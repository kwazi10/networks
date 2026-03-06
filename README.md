# Stage 2: Unified Networked Chat Application Prototype

**Team Members:** Kwazi Mbhokane, Siyabonga Ground, Isiphile Mkiwane

## Project Overview
This project is a multi-threaded, networked chat application that utilizes a hybrid Client-Server and Peer-to-Peer (P2P) architecture. It demonstrates reliable text-based communication over TCP and high-speed media transfers over connectionless UDP.

The application is built using a custom ASCII protocol, complete with structured headers (MessageType, Command, SenderID, RecipientID) and dynamic payload separation, completely eliminating the need for external serialization libraries like JSON.

## Core Features
* **Hybrid Architecture:** A Central Server manages session state, IP directory lookups, and TCP message routing, while clients dynamically open background UDP sockets for direct P2P media transfers.
* **TCP Group Chat (Megaphone):** The server acts as a central hub, receiving messages and broadcasting them to all active users simultaneously.
* **TCP Private Messaging (Post Office):** Users can send direct messages to specific peers. The central server parses the `RecipientID` header and routes the message exclusively to the target's socket.
* **UDP Media Multicast:** Clients can blast files to a single peer or multicast to the entire group using UDP. The system automatically attaches a `META:` packet containing the file name before streaming the 1024-byte data chunks, ensuring the receiving end saves the file correctly.
* **Dynamic Network Binding:** The server auto-detects its LAN IPv4 address and binds to `0.0.0.0`, allowing effortless cross-machine testing without hardcoding IP addresses. 

## Included Files
1. `config.py` - Contains shared network constants (Ports, Buffer Sizes, Encoding).
2. `helpers.py` - The protocol engine. Handles encoding, decoding, and parsing the custom ASCII headers.
3. `server.py` - The central multi-threaded TCP server and IP directory.
4. `client.py` - The unified end-user application running simultaneous TCP and UDP threads.

## How to Run & Test the Application

### 1. Start the Server
1. Open a terminal and run: `python server.py`
2. The server will display its active LAN IP address and Port. 

### 2. Connect the Clients
1. Open two or more separate terminals (these can be on the same machine or different machines on the same Wi-Fi network).
2. Run: `python client.py`
3. Enter the Server's IP address when prompted (or press `Enter` to default to `127.0.0.1` if testing locally).
4. Enter a unique username.

### 3. Testing the Commands
Once multiple clients are logged in, use the following commands to evaluate the system:

* **Group Chat:** Simply type a message and press Enter. It will broadcast to everyone.
* **Private Message:** Type `/msg <username> <message>` 
  * *Example:* `/msg Siyabonga Are you ready for the presentation?`
* **Directory Lookup:** Type `/lookup <username>` to ask the server for a peer's IP and dynamic UDP port.
* **Single Peer UDP File Transfer:** Type `/sendfile <username> <filename>`
  * *Example:* `/sendfile Isiphile diagram.png`
  * *(Note: If the file does not exist locally, the client will auto-generate a 5MB dummy file for transfer testing purposes).*
* **Group UDP Media Multicast:** Type `/sendfile GROUP <filename>`
  * *Example:* `/sendfile GROUP video.mp4`

**Testing Note:** Incoming files are automatically saved with a `received_` prefix to prevent overwriting local files when testing the sender and receiver on the exact same machine.
