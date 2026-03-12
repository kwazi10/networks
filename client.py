# ==========================================
# client.py
# GUI-Ready Chat Client
# ==========================================
import socket
import threading
import config
import helpers
import os
import time

pending_target = None
pending_file = None

# ==========================================
# SECTION 1: BACKGROUND FILE TRANSFERS
# ==========================================
def listen_for_udp_files(udp_socket):
    file_open = False
    f = None
    filename = "received_file.dat" 
    
    while True:
        try:
            data, addr = udp_socket.recvfrom(4096)
            
            if data.startswith(b"META:"):
                original_name = data[5:].decode(config.ENCODING)
                filename = f"received_{original_name}" 
                
                if file_open and f: f.close()
                f = open(filename, "wb")
                file_open = True
                
                print(f"\n[App]: Receiving file '{filename}'...")
                print(" > ", end="", flush=True)
                
            elif data == b"EOF":
                if f:
                    f.close()
                    file_open = False
                print(f"\n[App]: File received successfully! Saved as '{filename}'")
                print(" > ", end="", flush=True)
            else:
                if file_open and f:
                    f.write(data)
        except Exception:
            break

def send_file_udp_task(targets, filepath):
    filename = os.path.basename(filepath)
    
    if not os.path.exists(filepath):
        print(f"\n[App]: Test file '{filename}' created for sending...")
        with open(filepath, 'wb') as dummy:
            dummy.write(os.urandom(5 * 1024 * 1024)) 

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    if len(targets) > 1:
        print(f"\n[App]: Sending '{filename}' to the group...")
    else:
        print(f"\n[App]: Sending '{filename}'...")
    
    start_time = time.time()
    
    meta_packet = b"META:" + filename.encode(config.ENCODING)
    for ip, port in targets:
        udp_socket.sendto(meta_packet, (ip, port))
        
    time.sleep(0.05) 
    
    with open(filepath, 'rb') as file:
        while True:
            chunk = file.read(1024) 
            if not chunk: break
            for ip, port in targets:
                udp_socket.sendto(chunk, (ip, port))
            time.sleep(0.001)
            
    for ip, port in targets:
        udp_socket.sendto(b"EOF", (ip, port))
        
    end_time = time.time()
    print(f"\n[App]: File sent successfully in {round(end_time - start_time, 1)} seconds.")
    print(" > ", end="", flush=True)
    udp_socket.close()

# ==========================================
# SECTION 2: CHAT INTERFACE AND NOTIFICATIONS
# ==========================================
def display_help():
    """Prints a user-friendly manual for the application commands."""
    print("\n=================== APPLICATION MENU ===================")
    print(" /creategroup <name>     : Create a new custom chat group.")
    print(" /invite <group> <user>  : Invite a user to a group.")
    print(" /join <group>           : Accept an invite and join a group.")
    print(" /gmsg <group> <text>    : Send a message to a specific group.")
    print(" /gfile <group> <file>   : Send a file securely to a group.")
    print(" /online                 : View a list of all online users.")
    print(" /request <username>     : Request a secure private connection with a user.")
    print(" /accept <username>      : Accept a user's private connection request.")
    print(" /msg <username> <text>  : Send a private message (requires an accepted request).")
    print(" /sendfile <user> <file> : Send a file securely to a private user.")
    print(" /help                   : Display this instruction menu.")
    print(" exit                    : Close the application.")
    print("========================================================")

def receive_tcp_messages(sock):
    global pending_target, pending_file
    while True:
        try:
            raw_bytes = sock.recv(config.BUFFER_SIZE)
            if not raw_bytes: break
                
            headers, body = helpers.parse_message(helpers.decode_message(raw_bytes))
            
            # --- Text Messages ---
            if headers.get("MessageType") == "DATA" and headers.get("Command") == "TEXT":
                sender = headers.get("SenderID")
                recipient = headers.get("RecipientID")
                
                print(f"\n[{sender} to {recipient}]: {body}")
                print(" > ", end="", flush=True) 
                
            # --- Background Locating for Files ---
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "PEER_INFO":
                target_ip = body.split(":")[0]
                target_port = int(body.split(":")[1])
                
                if pending_file:
                    targets = [(target_ip, target_port)]
                    threading.Thread(target=send_file_udp_task, args=(targets, pending_file), daemon=True).start()
                    pending_file = None 
                    pending_target = None
                    
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "GROUP_INFO":
                if not body:
                    print("\n[App]: No other users are currently online to receive the file.")
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

            # --- User Interface Notifications ---
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "ONLINE_LIST":
                print(f"\n[App]: Users currently online: {body}")
                print(" > ", end="", flush=True)

            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "DM_REQUEST":
                sender_requesting = body
                print(f"\n[Notification]: '{sender_requesting}' wants to open a private connection with you! Type '/accept {sender_requesting}' to allow.")
                print(" > ", end="", flush=True)
                
            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "GROUP_INVITE":
                try:
                    group_name, owner = body.split(":", 1)
                    print(f"\n[Notification]: '{owner}' invited you to join group '{group_name}'! Type '/join {group_name}' to enter.")
                except ValueError:
                    pass
                print(" > ", end="", flush=True)

            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "INFO":
                print(f"\n[Notification]: {body}")
                print(" > ", end="", flush=True)

            elif headers.get("MessageType") == "CONTROL" and headers.get("Command") == "ERROR":
                print(f"\n[Error]: {body}")
                print(" > ", end="", flush=True)
                pending_file = None 
                
        except Exception:
            break

def start_protocol_client():
    global pending_target, pending_file
    
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('0.0.0.0', 0)) 
    my_udp_port = udp_socket.getsockname()[1]
    threading.Thread(target=listen_for_udp_files, args=(udp_socket,), daemon=True).start()
    
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print("--- Welcome to the Chat Application ---")
        target_server_ip = input("Enter the Server IP Address (or press Enter for default): ").strip()
        if target_server_ip == "":
            target_server_ip = '127.0.0.1'
            
        print(f"[*] Connecting...")
        client_socket.connect((target_server_ip, config.SERVER_PORT))
        print(f"[App]: Connected to server!\n")
        
        while True:
            print("=====================================")
            print("1. Login to an existing account")
            print("2. Create a new account")
            print("=====================================")
            choice = input("Select an option (1 or 2): ").strip()
            
            if choice not in ['1', '2']:
                print("[-] Invalid choice. Please type 1 or 2.")
                continue
                
            cmd_type = "LOGIN" if choice == '1' else "REGISTER"
            
            my_username = input("Username: ").strip()
            my_password = input("Password: ").strip()

            login_body = f"{my_password}:{my_udp_port}"
            login_string = helpers.build_message("COMMAND", cmd_type, my_username, "SERVER", body=login_body)
            client_socket.sendall(helpers.encode_message(login_string))

            reply_bytes = client_socket.recv(config.BUFFER_SIZE)
            if not reply_bytes:
                print("[Error]: Server disconnected.")
                return

            headers, body = helpers.parse_message(helpers.decode_message(reply_bytes))
            print(f"\n[Notification]: {body}")

            if headers.get("Command") == "ACK":
                break 

        threading.Thread(target=receive_tcp_messages, args=(client_socket,), daemon=True).start()

        display_help()
        
        while True:
            chat_text = input(" > ").strip()
            if chat_text.lower() == 'exit': 
                break 
                
            if not chat_text:
                continue
                
            if chat_text == "/help":
                display_help()
                continue
                
            if chat_text == "/online":
                req_msg = helpers.build_message("COMMAND", "ONLINE_USERS", my_username, "SERVER")
                client_socket.sendall(helpers.encode_message(req_msg))
                continue
                
            if chat_text.startswith("/request "):
                parts = chat_text.split(" ")
                if len(parts) >= 2:
                    target_user = parts[1]
                    req_msg = helpers.build_message("COMMAND", "REQUEST_DM", my_username, target_user)
                    client_socket.sendall(helpers.encode_message(req_msg))
                else:
                    print("[App]: Incorrect format. Type -> /request <username>")
                continue

            if chat_text.startswith("/accept "):
                parts = chat_text.split(" ")
                if len(parts) >= 2:
                    target_user = parts[1]
                    accept_msg = helpers.build_message("COMMAND", "ACCEPT_DM", my_username, target_user)
                    client_socket.sendall(helpers.encode_message(accept_msg))
                else:
                    print("[App]: Incorrect format. Type -> /accept <username>")
                continue 

            if chat_text.startswith("/msg "):
                parts = chat_text.split(" ", 2) 
                if len(parts) >= 3:
                    target_user = parts[1]
                    private_message = helpers.build_message("DATA", "TEXT", my_username, target_user, parts[2])
                    client_socket.sendall(helpers.encode_message(private_message))
                else:
                    print("[App]: Incorrect format. Type -> /msg <username> <message>")
                continue 
                
            if chat_text.startswith("/sendfile "):
                parts = chat_text.split(" ")
                if len(parts) >= 3:
                    pending_target = parts[1]
                    pending_file = parts[2]
                    lookup_msg = helpers.build_message("COMMAND", "PEER_LOOKUP", my_username, pending_target)
                    client_socket.sendall(helpers.encode_message(lookup_msg))
                else:
                    print("[App]: Incorrect format. Type -> /sendfile <username> <filename>")
                continue 

            # --- NEW GROUP COMMANDS ---
            if chat_text.startswith("/creategroup "):
                parts = chat_text.split(" ", 1)
                if len(parts) >= 2:
                    group_name = parts[1]
                    msg = helpers.build_message("COMMAND", "CREATE_GROUP", my_username, "SERVER", group_name)
                    client_socket.sendall(helpers.encode_message(msg))
                else:
                    print("[App]: Incorrect format. Type -> /creategroup <name>")
                continue

            if chat_text.startswith("/invite "):
                parts = chat_text.split(" ")
                if len(parts) >= 3:
                    group_name = parts[1]
                    target_user = parts[2]
                    msg = helpers.build_message("COMMAND", "INVITE_GROUP", my_username, "SERVER", f"{group_name}:{target_user}")
                    client_socket.sendall(helpers.encode_message(msg))
                else:
                    print("[App]: Incorrect format. Type -> /invite <groupname> <username>")
                continue

            if chat_text.startswith("/join "):
                parts = chat_text.split(" ", 1)
                if len(parts) >= 2:
                    group_name = parts[1]
                    msg = helpers.build_message("COMMAND", "ACCEPT_GROUP", my_username, "SERVER", group_name)
                    client_socket.sendall(helpers.encode_message(msg))
                else:
                    print("[App]: Incorrect format. Type -> /join <groupname>")
                continue

            if chat_text.startswith("/gmsg "):
                parts = chat_text.split(" ", 2)
                if len(parts) >= 3:
                    group_name = parts[1]
                    text = parts[2]
                    msg = helpers.build_message("DATA", "TEXT", my_username, group_name, text)
                    client_socket.sendall(helpers.encode_message(msg))
                else:
                    print("[App]: Incorrect format. Type -> /gmsg <groupname> <message>")
                continue

            if chat_text.startswith("/gfile "):
                parts = chat_text.split(" ")
                if len(parts) >= 3:
                    pending_target = parts[1] # Target is now the group name
                    pending_file = parts[2]
                    lookup_msg = helpers.build_message("COMMAND", "PEER_LOOKUP", my_username, pending_target)
                    client_socket.sendall(helpers.encode_message(lookup_msg))
                else:
                    print("[App]: Incorrect format. Type -> /gfile <groupname> <filename>")
                continue 

            if not chat_text.startswith("/"):
                print("[App]: Global chat is disabled. Please use /gmsg <groupname> <message> or /msg <username> <message>.")

    except Exception as e:
        print(f"\n[Error]: Disconnected from server.")
    finally:
        client_socket.close()

if __name__ == "__main__":
    start_protocol_client()