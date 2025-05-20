from  pythonosc import udp_client

client = udp_client.SimpleUDPClient("127.0.0.1", 7000)

client.send_message("/composition/layers/1/clips/1/connect", 1)


