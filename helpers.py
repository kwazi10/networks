# ==========================================
# helpers.py
# Handles byte encoding and protocol parsing
# ==========================================
import config

def encode_message(text_string):
    """Converts a standard Python string into transmittable bytes."""
    return text_string.encode(config.ENCODING)

def decode_message(byte_data):
    """Converts received network bytes back into a readable Python string."""
    return byte_data.decode(config.ENCODING)

def build_message(msg_type, command, sender_id, recipient_id, body=""):
    """
    Constructs the ASCII protocol string.
    Format explicitly separates Headers and Body using double line breaks (\r\n\r\n).
    """
    content_length = len(body.encode(config.ENCODING))
    
    header = f"MessageType: {msg_type}\r\n" \
             f"Command: {command}\r\n" \
             f"SenderID: {sender_id}\r\n" \
             f"RecipientID: {recipient_id}\r\n" \
             f"SequenceNum: 0\r\n" \
             f"ContentLength: {content_length}\r\n\r\n"
             
    return header + body

def parse_message(raw_string):
    """
    Parses an incoming protocol string into a dictionary of Headers and a Body string.
    This allows the server and client to easily read routing instructions.
    """
    # Split the message at the first double blank line
    parts = raw_string.split('\r\n\r\n', 1)
    header_block = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    
    headers = {}
    header_lines = header_block.split('\r\n')
    for line in header_lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key] = value
            
    return headers, body