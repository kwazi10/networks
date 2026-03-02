#Server for the chat room

import threading #Crucial for handling multiple clients at the same time
import socket #manages the connection between the server and the clients

host = '127.0.0.1' #this is my local server
port = 58000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port)) #binding the server to the host
server.listen(1) #listening for clients to connect, the number is the amount of clients that can be connected at the same time, we can change this number to allow more clients to connect

clients = []    #why are we creating a list for clients?, Should we create an ID generator for the each client
aliases = []

def broadcast(message):
    for client in clients:
        client.send(message)

def client_handling(client):
    while True:
        try:
            message = client.recv(1024)
            broadcast(message)
        except:
            index = clients.index(client) #searches the tuples for an index value, in our case its the client that has the bad connection
            clients.remove(client)
            client.close()
            alias = aliases[index]
            broadcast(f'{alias} has left the chat room!'.encode('utf-8'))
            aliases.remove(alias)
            break

#Main function that handles the incoming connections
def receive():
    while True:
        print('Server is running and listening...')
        client, address = server.accept()
        print(f'Connection is established with {str(address)}')
        client.send('ALIAS'.encode('utf-8'))
        alias = client.recv(1024) #tells us the alias of the client that just connected
        aliases.append(alias)
        clients.append(client)
        print(f'The alias of the client is {alias}'.encode('utf-8'))
        broadcast(f'{alias} has joined the chat room!'.encode('utf-8'))
        client.send('Connected to the server!'.encode('utf-8'))
        client_handling_thread = threading.Thread(target=client_handling, args=(client,))
        client_handling_thread.start()

receive()