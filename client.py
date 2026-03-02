import socket
import threading

port = 58000
host = '127.0.0.1'

alias = input('Choose an alias: ')
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #creating a socket object that will be used to connect to the server, we are using the AF_INET address family and the SOCK_STREAM socket type, which means we are using TCP protocol for communication
client.connect((host, port))#sending a connection request to the server, we are using the connect method of the socket object and passing the host and port as arguments

def receive():
    while True:
        try:
            message = client.recv(1024).decode('utf-8') #receiving messages from the server, we are using the recv method of the socket object and passing the buffer size as an argument, we are also decoding the message from bytes to string using the decode method
            if message == 'alias?': #if the message from the server is 'alias?' then we send the alias of the client to the server
                client.send(alias.encode('utf-8'))
            else:
                print(message) #if the message is not 'alias?' then we print the message to the console
        except:
            print('An error occurred!') #if there is an error while receiving messages from the server, we print an error message to the console
            client.close() #closing the connection to the server
            break

def client_send():
    while True:
        message = f'{alias}: {input("")}' #getting the message from the user and adding the alias of the client to the message
        client.send(message.encode('utf-8')) #sending the message to the server, we are using the send method of the socket object and passing the message as an argument, we are also encoding the message from string to bytes using the encode method

receive_thread = threading.Thread(target=receive) #creating a thread for receiving messages from the server, we are using the Thread class from the threading module and passing the receive function as the target
receive_thread.start() #starting the thread for receiving messages from the server

client_send_thread = threading.Thread(target=client_send) #creating a thread for sending messages to the server
client_send_thread.start() #starting the thread for sending messages to the server