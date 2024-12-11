import socket
import threading
import pickle

rooms = {}
clients = {}

class Room:
    def __init__(self, name, admin_name):
        self.name = name
        self.clients = []
        self.cities = set()
        self.last_city = None
        self.banned = set()
        self.timer = None
        self.points = {}
        self.admin_name = admin_name
        self.current_turn_index = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

    def broadcast(self, message, exclude=None):
        for client, _ in self.clients:
            if client != exclude:
                client.send(pickle.dumps(message))

    def next_turn(self):
        with self.lock:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.clients)
            self.condition.notify_all()

    def get_current_player(self):
        return self.clients[self.current_turn_index]

    def add_client(self, client, name):
        with self.lock:
            self.clients.append((client, name))
            if name not in self.points:
                self.points[name] = 0
            self.broadcast(f"{name} присоединился к комнате {self.name}!")
            if len(self.clients) >= 2:
                self.condition.notify_all()

    def remove_client(self, client, name):
        with self.lock:
            self.clients = [(c, n) for c, n in self.clients if c != client]
            self.broadcast(f"{name} покинул комнату {self.name}.")
            if self.current_turn_index >= len(self.clients):
                self.current_turn_index = 0
            if len(self.clients) < 2:
                self.broadcast("В комнате недостаточно игроков для продолжения игры.")
                self.condition.notify_all()

    def reset_timer(self, name):
        if self.timer:
            self.timer.cancel()

        self.timer = threading.Timer(30.0, self.timeout, args=(name,))
        self.timer.start()

    def timeout(self, name):
        self.broadcast(f"Игрок {name} не успел ответить!")
        self.game_over()

    def game_over(self):
        with self.lock:
            winner = max(self.points, key=self.points.get, default=None)
            self.broadcast(f"Игра завершена! Победитель: {winner}, Очки: {self.points}")
            for client, _ in self.clients:
                client.close()
            self.clients.clear()
            del rooms[self.name]

    def ban_player(self, name, requester):
        with self.lock:
            if requester != self.admin_name:
                return f"Только администратор может блокировать игроков!"
            if name in self.banned:
                return f"Игрок {name} уже заблокирован."
            self.banned.add(name)
            self.broadcast(f"Игрок {name} был заблокирован!")

def handle_client(client):
    try:
        client.send(pickle.dumps("Введите ваше имя: "))
        name = pickle.loads(client.recv(1024)).strip()
        clients[client] = name
        client.send(pickle.dumps("Добро пожаловать! Выберите комнату или создайте новую."))

        while True:
            client.send(pickle.dumps("Введите команду (создать <комната>, присоединиться <комната>, список): "))
            command = pickle.loads(client.recv(1024)).strip()

            if command.startswith("создать "):
                room_name = command.split(" ", 1)[1]
                if room_name not in rooms:
                    rooms[room_name] = Room(room_name, admin_name=name)
                    client.send(pickle.dumps(f"Комната {room_name} создана. Вы стали администратором."))
                else:
                    client.send(pickle.dumps(f"Комната {room_name} уже существует."))

            elif command.startswith("присоединиться "):
                room_name = command.split(" ", 1)[1]
                if room_name in rooms:
                    room = rooms[room_name]
                    if name in room.banned:
                        client.send(pickle.dumps(f"Вы заблокированы в комнате {room_name}."))
                    else:
                        room.add_client(client, name)
                        play_game(client, room)
                        break
                else:
                    client.send(pickle.dumps(f"Комната {room_name} не существует."))

            elif command == "список":
                if rooms:
                    room_list = list(rooms.keys())
                    client.send(pickle.dumps(room_list))
                else:
                    client.send(pickle.dumps(["Нет доступных комнат."]))

            elif command.startswith("перейти "):
                new_room_name = command.split(" ", 1)[1]
                if new_room_name in rooms:
                    new_room = rooms[new_room_name]
                    if name in new_room.banned:
                        client.send(pickle.dumps(f"Вы заблокированы в комнате {new_room_name}."))
                    else:
                        current_room = next((r for r in rooms.values() if (client, name) in r.clients), None)
                        if current_room:
                            current_room.remove_client(client, name)
                        new_room.add_client(client, name)
                        play_game(client, new_room)
                        break
                else:
                    client.send(pickle.dumps(f"Комната {new_room_name} не существует."))
            else:
                client.send(pickle.dumps("Неправильная команда. Попробуйте снова."))
    finally:
        if client in clients:
            del clients[client]
        client.close()


def play_game(client, room):
    name = clients[client]

    with room.lock:
        while len(room.clients) < 2:
            client.send(pickle.dumps("Ожидаем второго игрока..."))
            room.condition.wait()

    room.broadcast(f"Игра началась в комнате {room.name}!")

    while True:
        with room.lock:
            while room.get_current_player()[0] != client:
                room.condition.wait()

            client.send(pickle.dumps("Ваш ход: "))

        try:
            msg = pickle.loads(client.recv(1024)).strip()

            if msg.lower() == "exit":
                room.remove_client(client, name)
                client.close()
                break

            elif msg.lower().startswith("ban "):
                to_ban = msg.split(" ", 1)[1]
                response = room.ban_player(to_ban, name)
                client.send(pickle.dumps(response))

            elif msg.lower() not in room.cities:
                if room.last_city is None or msg.lower()[0] == room.last_city[-1]:
                    room.cities.add(msg.lower())
                    room.last_city = msg.lower()
                    room.points[name] += 1
                    room.broadcast(f"{name} назвал город: {msg}. Очки: {room.points[name]}")
                    room.reset_timer(name)
                    room.next_turn()
                else:
                    client.send(pickle.dumps("Город должен начинаться на последнюю букву предыдущего!"))
            else:
                client.send(pickle.dumps("Этот город уже был назван!"))

        except Exception as e:
            print(f"Ошибка: {e}")
            room.remove_client(client, name)
            break


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 10003))
    server.listen(7)
    print("Сервер запущен. Ожидание подключений...")

    while True:
        client, address = server.accept()
        print(f"Новое подключение: {address}")
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
