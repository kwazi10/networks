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
    for incoming P2P file transfers from other clients.
    """
    file_open = False
    f = None
    save_filename = "p2p_received_media.mp4"

    while True:
        try:
            data, addr = udp_socket.recvfrom(4096)
            
            if data.startswith(b"FILENAME:"):
                raw_name = data.decode(config.ENCODING).split(":", 1)[1]
                save_filename = os.path.basename(raw_name)
                continue

            if data == b"EOF":
                if f:
                    f.close()
                    file_open = False
                print(f"\n[P2P SYSTEM]: Incoming media transfer complete! Saved as '{save_filename}'")
                print(" > ", end="", flush=True) # Reset UI prompt
                save_filename = "p2p_received_media.mp4"
            else:
                # Open the file container on the first packet received
                if not file_open:
                    f = open(save_filename, "wb")
                    file_open = True
                f.write(data)
        except Exception:
            break

def send_file_udp_task(target_ip, target_port, filepath):
    """
    Spawns temporarily to blast a file over connectionless UDP.
    Auto-generates dummy files if the requested file doesn't exist to allow easy testing.
    """
    if not os.path.exists(filepath):
        print(f"\n[SYSTEM] Auto-generating 5MB dummy file '{filepath}' for transfer test...")
        with open(filepath, 'wb') as dummy:
            dummy.write(os.urandom(5 * 1024 * 1024)) 

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"\n[P2P SYSTEM]: Blasting '{filepath}' to {target_ip}:{target_port} via UDP...")
    
    # Send filename header
    filename = os.path.basename(filepath)
    udp_socket.sendto(f"FILENAME:{filename}".encode(config.ENCODING), (target_ip, target_port))
    time.sleep(0.02)

    start_time = time.time()
    with open(filepath, 'rb') as file:
        while True:
            chunk = file.read(4096) # Standard safe UDP packet size
            if not chunk: 
                break
            udp_socket.sendto(chunk, (target_ip, target_port))
            time.sleep(0.001) # Prevent local buffer overflow
            
    # Send the End Of File flag so the receiver knows to stop listening
    udp_socket.sendto(b"EOF", (target_ip, target_port))
    end_time = time.time()
    
    print(f"\n[P2P SYSTEM]: Transfer finished in {round(end_time - start_time, 4)} seconds!")
    print(" > ", end="", flush=True)
    udp_socket.close()

# ==========================================
# SECTION 2: TCP CLIENT & UI INTERFACE
# ==========================================
def receive_tcp_messages(sock):
    """
    Runs in a background thread. Listens for server broadcasts, 
    private messages, and directory lookup responses.
    """
    global pending_target, pending_file
    while True:
        try:
            raw_bytes = sock.recv(config.BUFFER_SIZE)
            if not raw_bytes: 
                break
                
            headers, body = helpers.parse_message(helpers.decode_message(raw_bytes))
            
            # --- SCENARIO A: Text Message Display ---
            if headers.get("MessageType") == "DATA" and headers.get("Command") == "TEXT":
                sender = headers.get("SenderID")
                recipient = headers.get("RecipientID")
                
                if recipient == "GROUP":
                    print(f"\n[{sender} to GROUP]: {body}")
                else:
                    print(f"\n[PRIVATE from {sender}]: {body}")
                print(" > ", end="", flush=True) 
                
            # --- SCENARIO B: P2P Directory Lookup Response ---
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "PEER_INFO":
                ip_and_port = body
                target_ip = ip_and_port.split(":")[0]
                target_port = int(ip_and_port.split(":")[1])
                
                # If we initiated a /sendfile command, trigger the UDP thread now!
                if pending_file:
                    threading.Thread(target=send_file_udp_task, args=(target_ip, target_port, pending_file), daemon=True).start()
                    pending_file = None 
                    pending_target = None
                else:
                    # Otherwise, it was just a manual /lookup command
                    print(f"\n[SERVER DIRECTORY]: Peer is at {ip_and_port}")
                    print(" > ", end="", flush=True)
                    
            # --- SCENARIO C: Server Errors ---
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
    
    # Start the UDP listener in the background
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
                    # Ask server for IP. The background TCP thread will catch the reply and start the transfer.
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