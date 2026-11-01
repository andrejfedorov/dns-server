import socket
import socketserver
import struct
import threading

def parse_query(data):
    offset = 12
    name = []
    while True:
        length = data[offset]
        if length == 0:
                offset += 1
                break
        name.append(data[offset+1 : offset+1+length].decode('utf-8', errors='ignore'))
        offset += length + 1
    request_type = struct.unpack('>H', data[offset:offset+2])[0]
    return data[:2], ".".join(name), request_type

def build_response(tx_id, name, request_type, data, ttl=300):
    header = tx_id + b'\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00'
    question = b"".join(bytes([len(p)]) + p.encode('utf-8') for p in name.split('.')) + b'\x00'
    question += struct.pack('>H', request_type) + b'\x00\x01'

    if not data:
        return header + question

    answer = b'\xc0\x0c' + struct.pack('>H', request_type) + b'\x00\x01'
    answer += struct.pack('>I', ttl) + struct.pack('>H', len(data)) + data
    return header + question + answer

class DNSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            request_data, client_socket = self.request

            transaction_id, domain_name, request_type = parse_query(request_data)
            print(f"Запрос: {domain_name} (Type: {request_type})")

            upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            upstream_socket.settimeout(3)
            upstream_socket.sendto(request_data, ("8.8.8.8", 53))
            upstream_response, _ = upstream_socket.recvfrom(512)
            upstream_socket.close()

            offset = 12
            while upstream_response[offset] != 0:
                offset += upstream_response[offset] + 1
            offset += 5
            if upstream_response[offset] == 0xc0:
                offset += 2
            else:
                while upstream_response[offset] != 0:
                    offset += upstream_response[offset] + 1
                offset += 1

            answer_data_length = struct.unpack('>H', upstream_response[offset + 8 : offset + 10])[0]
            answer_data = upstream_response[offset + 10 : offset + 10 + answer_data_length]

            response_packet = build_response(transaction_id, domain_name, request_type, answer_data)
            client_socket.sendto(response_packet, self.client_address)
        except Exception as error:
            print(f"error: {error}")


class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    allow_reuse_address = True


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    udp_server = ThreadedUDPServer(('0.0.0.0', 53), DNSHandler)
    tcp_server = ThreadedTCPServer(('0.0.0.0', 53), DNSHandler)

    threading.Thread(target=udp_server.serve_forever, daemon=True).start()
    threading.Thread(target=tcp_server.serve_forever, daemon=True).start()

    print("Сервер запущен")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        udp_server.shutdown()
        tcp_server.shutdown()
