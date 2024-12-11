import socket
import threading
import pickle


def receive_messages(sock):
    while True:
        try:
            data = sock.recv(1024)
            msg = pickle.loads(data)
            print(msg)
        except Exception as e:
            print("Соединение с сервером потеряно.", e)
            break


def send_message(sock):
    while True:
        try:
            msg = input()
            sock.send(pickle.dumps(msg))
            if msg.lower() == "exit":
                print("Вы вышли из игры.")
                break
        except Exception as e:
            print("Ошибка при отправке сообщения:", e)
            break


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 10003))
    print("Подключение к серверу выполнено.")
    threading.Thread(target=receive_messages, args=(sock,), daemon=True).start()
    send_message(sock)
    sock.close()


if __name__ == "__main__":
    main()
