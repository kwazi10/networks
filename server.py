# ==========================================
# server.py
# Central multi-threaded TCP Server & Directory
# ==========================================
import socket
import threading
import config
import helpers

active_users = {}
registered_users = {}
approved_dms = {}

def load_users(filename="users.txt"):
    global registered_users
    try:
        with open(filename, "r") as f:
            for line in f:
                parts = line.strip().split(" ", 1)
                if len(parts) == 2:
                    username, password = parts
                    registered_users[username] = password
        print(f"[*] Loaded {len(registered_users)} users from {filename}.")
    except FileNotFoundError:
        print(f"[!] WARNING: {filename} not found. All logins will fail.")
    except Exception as e:
        print(f"[!] ERROR: Could not load users from {filename}. {e}")

def save_new_user(username, password, filename="users.txt"):
    global registered_users
    try:
        with open(filename, "a") as f:
            f.write(f"\n{username} {password}")
    except Exception as e:
        print(f"[!] ERROR: Could not save new user to {filename}. {e}")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def handle_client(conn, addr):
    current_user = None 
    
    try:
        while True:
            raw_bytes = conn.recv(config.BUFFER_SIZE)
            if not raw_bytes: 
                break 
            
            headers, body = helpers.parse_message(helpers.decode_message(raw_bytes))
            command = headers.get("Command")
            sender = headers.get("SenderID")
            recipient = headers.get("RecipientID")
            
            # --- ACCOUNT REGISTRATION ---
            if command == "REGISTER":
                try:
                    password, client_udp_port = body.split(":", 1)
                except ValueError:
                    continue

                if sender in registered_users:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"Username '{sender}' is already taken. Please login.")
                    conn.sendall(helpers.encode_message(error_msg))
                    continue
                
                registered_users[sender] = password
                save_new_user(sender, password)
                
                current_user = sender
                client_ip = addr[0] if addr[0] != '127.0.0.1' else get_local_ip()
                
                active_users[current_user] = {"conn": conn, "ip": client_ip, "udp_port": client_udp_port}
                ack_msg = helpers.build_message("CONTROL", "ACK", "SERVER", current_user, "Account created! You are now logged in.")
                conn.sendall(helpers.encode_message(ack_msg))
                continue

            # --- CLIENT LOGIN ---
            elif command == "LOGIN":
                try:
                    password, client_udp_port = body.split(":", 1)
                except ValueError:
                    continue

                if sender in active_users:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"User '{sender}' is already logged in elsewhere.")
                    conn.sendall(helpers.encode_message(error_msg))
                    continue

                if sender in registered_users and registered_users[sender] == password:
                    current_user = sender
                    client_ip = addr[0] if addr[0] != '127.0.0.1' else get_local_ip()
                    
                    active_users[current_user] = {"conn": conn, "ip": client_ip, "udp_port": client_udp_port}
                    ack_msg = helpers.build_message("CONTROL", "ACK", "SERVER", current_user, "Login successful!")
                    conn.sendall(helpers.encode_message(ack_msg))
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, "Invalid username or password.")
                    conn.sendall(helpers.encode_message(error_msg))
                continue

            # --- FETCH ONLINE USERS ---
            elif command == "ONLINE_USERS":
                online_list = [u for u in active_users.keys() if u != sender]
                users_str = ", ".join(online_list) if online_list else "No one else is currently online."
                reply = helpers.build_message("CONTROL", "ONLINE_LIST", "SERVER", sender, users_str)
                conn.sendall(helpers.encode_message(reply))

            # --- FORMAL CONNECTION REQUEST ---
            elif command == "REQUEST_DM":
                target_user = recipient
                if target_user in active_users:
                    if target_user == sender:
                        error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, "You cannot request a connection with yourself.")
                        conn.sendall(helpers.encode_message(error_msg))
                        continue
                        
                    notice = helpers.build_message("CONTROL", "INFO", "SERVER", sender, f"Connection request sent to {target_user}. Waiting for their approval...")
                    conn.sendall(helpers.encode_message(notice))
                    
                    req = helpers.build_message("CONTROL", "DM_REQUEST", "SERVER", target_user, sender)
                    active_users[target_user]["conn"].sendall(helpers.encode_message(req))
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"User '{target_user}' is offline.")
                    conn.sendall(helpers.encode_message(error_msg))

            # --- ACCEPT PRIVATE MESSAGES ---
            elif command == "ACCEPT_DM":
                target_user = recipient 
                
                if sender not in approved_dms:
                    approved_dms[sender] = set()
                approved_dms[sender].add(target_user)
                
                if target_user not in approved_dms:
                    approved_dms[target_user] = set()
                approved_dms[target_user].add(sender)
                
                ack = helpers.build_message("CONTROL", "INFO", "SERVER", sender, f"Connection established! You can now send private messages and files to {target_user}.")
                conn.sendall(helpers.encode_message(ack))
                
                if target_user in active_users:
                    notify = helpers.build_message("CONTROL", "INFO", "SERVER", target_user, f"{sender} accepted your request! You can now message them privately.")
                    active_users[target_user]["conn"].sendall(helpers.encode_message(notify))

            # --- GROUP CHAT ---
            elif command == "TEXT" and recipient == "GROUP":
                forward_msg = helpers.build_message("DATA", "TEXT", sender, "GROUP", body)
                encoded_msg = helpers.encode_message(forward_msg)
                
                for user, user_data in active_users.items():
                    if user != sender: 
                        try:
                            user_data["conn"].sendall(encoded_msg) 
                        except Exception:
                            pass

            # --- PRIVATE CHAT (STRICT APPROVAL) ---
            elif command == "TEXT" and recipient != "GROUP":
                target_user = recipient 
                
                if target_user in active_users:
                    if target_user in approved_dms and sender in approved_dms[target_user]:
                        forward_msg = helpers.build_message("DATA", "TEXT", sender, target_user, body)
                        try:
                            active_users[target_user]["conn"].sendall(helpers.encode_message(forward_msg))
                        except Exception:
                            pass
                    else:
                        error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"Connection rejected. Type '/request {target_user}' to establish a private channel first.")
                        conn.sendall(helpers.encode_message(error_msg))
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"User '{target_user}' is offline.")
                    conn.sendall(helpers.encode_message(error_msg))

            # --- P2P FILE DIRECTORY (STRICT APPROVAL) ---
            elif command == "PEER_LOOKUP":
                target_user = recipient 
                
                if target_user == "GROUP":
                    peers = [f"{info['ip']}:{info['udp_port']}" for user, info in active_users.items() if user != sender]
                    reply_body = ",".join(peers) 
                    reply_msg = helpers.build_message("CONTROL", "GROUP_INFO", "SERVER", sender, reply_body)
                    conn.sendall(helpers.encode_message(reply_msg))
                    
                elif target_user in active_users:
                    if target_user in approved_dms and sender in approved_dms[target_user]:
                        target_ip = active_users[target_user]["ip"]
                        target_udp = active_users[target_user]["udp_port"]
                        reply_body = f"{target_ip}:{target_udp}"
                        reply_msg = helpers.build_message("CONTROL", "PEER_INFO", "SERVER", sender, reply_body)
                        conn.sendall(helpers.encode_message(reply_msg))
                    else:
                        error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"Cannot send file. Type '/request {target_user}' to establish a private channel first.")
                        conn.sendall(helpers.encode_message(error_msg))
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, "User offline.")
                    conn.sendall(helpers.encode_message(error_msg))

    except ConnectionResetError:
        pass 
    finally:
        if current_user and current_user in active_users:
            del active_users[current_user]
            print(f"[-] {current_user} disconnected.")
        conn.close()

def start_threaded_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind(('0.0.0.0', config.SERVER_PORT))
    load_users() 
    server_socket.listen(5) 
    
    print("==================================================")
    print(f"[*] CENTRAL SERVER ONLINE")
    print(f"[*] Tell clients to connect to IP: {get_local_ip()}")
    print(f"[*] Port: {config.SERVER_PORT}")
    print("==================================================")

    try:
        while True: 
            conn, addr = server_socket.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_threaded_server()