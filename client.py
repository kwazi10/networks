# ==========================================
# client.py
# Unified multi-threaded TCP & UDP Client
# ==========================================
import socket
import threading
import config
import helpers
import os
import time

# Tracks P2P file transfer states
pending_target = None
pending_file = None

# ==========================================
# SECTION 1: UDP P2P MEDIA TRANSFER
# ==========================================
def listen_for_udp_files(udp_socket):
    """
    Runs in a background thread. Constantly listens on the dynamic UDP port 
    for incoming P2P file transfers and extracts the filename metadata.
    """
    file_open = False
    f = None
    filename = "p2p_received_media.file" 
    
    while True:
        try:
            data, addr = udp_socket.recvfrom(4096)
            
            # Catch the Metadata packet to extract the true filename
            if data.startswith(b"META:"):
                original_name = data[5:].decode(config.ENCODING)
                filename = f"received_{original_name}" 
                
                if file_open and f: f.close()
                f = open(filename, "wb")
                file_open = True
                
                print(f"\n[P2P SYSTEM]: Incoming file detected! Catching '{filename}'...")
                print(" > ", end="", flush=True)
                
            elif data == b"EOF":
                if f:
                    f.close()
                    file_open = False
                print(f"\n[P2P SYSTEM]: Media transfer complete! Saved successfully as '{filename}'")
                print(" > ", end="", flush=True)
            else:
                # Write the raw media bytes to the file
                if file_open and f:
                    f.write(data)
        except Exception:
            break

def send_file_udp_task(targets, filepath):
    """
    Spawns temporarily to blast a file over connectionless UDP.
    Can send to a single peer, or multicast to a list of multiple peers.
    """
    filename = os.path.basename(filepath)
    
    # Auto-generate dummy files if testing a file that doesn't exist locally
    if not os.path.exists(filepath):
        print(f"\n[SYSTEM] Auto-generating 5MB dummy file '{filepath}' for transfer test...")
        with open(filepath, 'wb') as dummy:
            dummy.write(os.urandom(5 * 1024 * 1024)) 

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"\n[P2P SYSTEM]: Blasting '{filename}' to {len(targets)} peer(s) via UDP...")
    
    start_time = time.time()
    
    # 1. Blast the Metadata (Filename) to all targets
    meta_packet = b"META:" + filename.encode(config.ENCODING)
    for ip, port in targets:
        udp_socket.sendto(meta_packet, (ip, port))
        
    time.sleep(0.05) # Allow receivers 50ms to open their local files
    
    # 2. Blast the File Chunks to all targets
    with open(filepath, 'rb') as file:
        while True:
            chunk = file.read(4096)
            if not chunk: break
            
            for ip, port in targets:
                udp_socket.sendto(chunk, (ip, port))
            time.sleep(0.001) # Prevent local buffer overflow
            
    # 3. Blast the EOF flag to all targets
    for ip, port in targets:
        udp_socket.sendto(b"EOF", (ip, port))
        
    end_time = time.time()
    print(f"\n[P2P SYSTEM]: Transfer finished in {round(end_time - start_time, 4)} seconds!")
    print(" > ", end="", flush=True)
    udp_socket.close()

# ==========================================
# SECTION 2: TCP CHAT CLIENT FUNCTIONS
# ==========================================
def receive_tcp_messages(sock):
    """
    Runs in a background thread. Listens for server text broadcasts, 
    private messages, and directory lookup responses.
    """
    global pending_target, pending_file
    while True:
        try:
            raw_bytes = sock.recv(config.BUFFER_SIZE)
            if not raw_bytes: break
                
            headers, body = helpers.parse_message(helpers.decode_message(raw_bytes))
            
            # --- SCENARIO A: Text Messages ---
            if headers.get("MessageType") == "DATA" and headers.get("Command") == "TEXT":
                sender = headers.get("SenderID")
                recipient = headers.get("RecipientID")
                
                if recipient == "GROUP":
                    print(f"\n[{sender} to GROUP]: {body}")
                else:
                    print(f"\n[PRIVATE from {sender}]: {body}")
                print(" > ", end="", flush=True) 
                
            # --- SCENARIO B: Single User IP Response ---
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "PEER_INFO":
                target_ip = body.split(":")[0]
                target_port = int(body.split(":")[1])
                
                if pending_file:
                    targets = [(target_ip, target_port)]
                    threading.Thread(target=send_file_udp_task, args=(targets, pending_file), daemon=True).start()
                    pending_file = None 
                    pending_target = None
                else:
                    print(f"\n[SERVER DIRECTORY]: Peer is at {body}")
                    print(" > ", end="", flush=True)
                    
            # --- SCENARIO C: Group IPs Response (Multicast Setup) ---
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "GROUP_INFO":
                if not body:
                    print("\n[SERVER DIRECTORY]: No other users online to receive the file.")
                    print(" > ", end="", flush=True)
                    pending_file = None
                    pending_target = None
                    continue
                
                targets = []
                for peer in body.split(","):
                    ip = peer.split(":")[0]
                    port = int(peer.split(":")[1])
                    targets.append((ip, port))
                    
                if pending_file:
                    threading.Thread(target=send_file_udp_task, args=(targets, pending_file), daemon=True).start()
                    pending_file = None 
                    pending_target = None

            # --- SCENARIO D: Errors ---
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "ERROR":
                print(f"\n[SERVER ERROR]: {body}")
                print(" > ", end="", flush=True)
                pending_file = None 
                
        except Exception:
            break

def start_protocol_client():
    """Initializes sockets, handles login, and runs the main user input loop."""
    global pending_target, pending_file
    
    # 1. Bind the UDP socket to a random dynamic port for receiving files
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('0.0.0.0', 0)) 
    my_udp_port = udp_socket.getsockname()[1]
    
    threading.Thread(target=listen_for_udp_files, args=(udp_socket,), daemon=True).start()
    
    # 2. Establish the primary TCP connection to the Central Server
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print("--- Chat Client Startup ---")
        target_server_ip = input("Enter Server IP (Press Enter for Localhost): ").strip()
        if target_server_ip == "":
            target_server_ip = '127.0.0.1'
            
        print(f"[*] Connecting to {target_server_ip}:{config.SERVER_PORT}...")
        client_socket.connect((target_server_ip, config.SERVER_PORT))
        
        my_username = input("Enter your username: ")

        # Hide our dynamic UDP port in the body of the Login message
        login_string = helpers.build_message("COMMAND", "LOGIN", my_username, "SERVER", body=str(my_udp_port))
        client_socket.sendall(helpers.encode_message(login_string))

        reply_bytes = client_socket.recv(config.BUFFER_SIZE)
        print(f"[*] Server replied: {helpers.parse_message(helpers.decode_message(reply_bytes))[1]}\n")

        # Start the TCP text listener in the background
        threading.Thread(target=receive_tcp_messages, args=(client_socket,), daemon=True).start()

        # 3. Main Interface Loop
        while True:
            chat_text = input(" > ")
            if chat_text.lower() == 'exit': 
                break 
                
            # COMMAND ROUTER:
            # 1. Private Messages (/msg)
            if chat_text.startswith("/msg "):
                parts = chat_text.split(" ", 2) 
                if len(parts) >= 3:
                    target_user = parts[1]
                    private_message = helpers.build_message("DATA", "TEXT", my_username, target_user, parts[2])
                    client_socket.sendall(helpers.encode_message(private_message))
                else:
                    print("Usage: /msg <username> <your message>")
                continue 
                
            # 2. P2P File Transfers (/sendfile)
            if chat_text.startswith("/sendfile "):
                parts = chat_text.split(" ")
                if len(parts) >= 3:
                    pending_target = parts[1]
                    pending_file = parts[2]
                    lookup_msg = helpers.build_message("COMMAND", "PEER_LOOKUP", my_username, pending_target)
                    client_socket.sendall(helpers.encode_message(lookup_msg))
                else:
                    print("Usage: /sendfile <username> <filename>")
                continue 
                
            # 3. Manual IP Lookup (/lookup)
            if chat_text.startswith("/lookup "):
                parts = chat_text.split(" ")
                if len(parts) > 1:
                    lookup_msg = helpers.build_message("COMMAND", "PEER_LOOKUP", my_username, parts[1])
                    client_socket.sendall(helpers.encode_message(lookup_msg))
                continue
                
            # DEFAULT: Broadcast to the Group
            chat_message = helpers.build_message("DATA", "TEXT", my_username, "GROUP", chat_text)
            client_socket.sendall(helpers.encode_message(chat_message))

    except Exception as e:
        print(f"[-] Disconnected. Error: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    start_protocol_client()
