from globals import *
from peer import *
from player import *

####
#### Инициализация всех необходимых для создания сессии переменных. Их значения нужно ввести в консоль во время первого запуска скрипта.
####

def init():
    # Этим глобальным переменным нужно будет присвоить значения, следовательно, стоит сделать их редактируемыми:
    global API_ID
    global API_HASH
    global BOT_TOKEN
    global client
    global conn
    global cursor

    # Открытие config.ini или его создание в случае отсутствия этого файла.
    # Config.ini создаётся в той же директории, где лежит script.py.
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))

    # Заполнение config.ini необходимыми полями в случае их отсутствия:
    if config.has_section('API') == False:
        print("Создание нового .ini файла...")
        config.add_section('API')
        id_input = input("Введите API id: ")
        hash_input = input("Введите API hash: ")
        bot_token_input = input("Введите токен вашего бота: ")
        config.set('API', 'id', id_input)
        config.set('API', 'hash', hash_input)
        config.set('API', 'token', bot_token_input)
        print("Запись файла config.ini...")
        config.write(open(os.path.join(os.path.dirname(__file__), 'config.ini'), 'w'))

    # Извлечение переменных из открытого config.ini. Открытие файла bot.session, хранящего сессию в Telegram, или его создание.
    API_ID = config.getint('API', 'id')
    API_HASH = config.get('API', 'hash')
    BOT_TOKEN = config.get('API', 'token')
    client = TelegramClient(os.path.join(os.path.dirname(__file__), 'bot'), API_ID, API_HASH).start(bot_token=BOT_TOKEN)

    # Открытие базы данных или её создание и заполнение нужными таблицами.
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'gamelogs.sqlite'), check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS GameScores('name' INTEGER, 'user_id' INTEGER, 'score' INTEGER, 'out_of' INTEGER, 'kicked' INTEGER DEFAULT 0, 'tour' INTEGER DEFAULT 1)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ChatsPreferences( 'chat_id' INTEGER, 'chat_name' TEXT, 'delete_immediately' INTEGER, 'clear_after_duel' INTEGER)")

    # Заполнение листа, содержащего все пиры, информация о которых есть в базе данных.
    cursor.execute("SELECT * FROM ChatsPreferences")
    chats_from_table = cursor.fetchall()
    for chat_from_table in chats_from_table:
        new_peer = Peer(*chat_from_table)
        peers.append(new_peer)

####
#### Различные служебные функции, в основном обновляющие базу данных.
####

# Ищет пир по его id в листе и возвращает его индекс.
async def get_peer_index_by_id(_id):
    for i in range(len(peers)):
        if peers[i].id == _id:
            return i

    # Если пир не находится, то создаётся новый и добавляется в лист.
    chat = await client.get_entity(await client.get_entity(_id))
    cursor.execute("INSERT INTO ChatsPreferences VALUES(:id, :name, 0, 0)", {'id':chat.id, 'name':chat.title})
    conn.commit()
    peers.append(Peer(chat.id, chat.title, 0, 0))
    return len(peers)-1

# Удаляет все сообщения с ложками по окончанию дуэли, если эта опция активирована в настройках конкретного чата.
async def delete_messages(peer_index):
    try:
        await client.delete_messages(peers[peer_index].input_peer, peers[peer_index].messages_with_spoon_ids)
        peers[peer_index].messages_with_spoon_ids = []
    except Exception as e:
        print(e)

# Удаляет из турнира игрока, который проиграл дуэль, проводящуюся в рамках турнира.
def user_kicked_tournament(_player):
    cursor.execute("UPDATE GameScores SET kicked=1, tour=0 WHERE user_id=:user_id",
                   {'user_id': _player.id})
    conn.commit()

# Переводит игрока, победившего в дуэли, проводящейся в рамках турнира, но следующий раунд/тур/уровень/придумать название.
def user_won_tournament(_player):
    cursor.execute("UPDATE GameScores SET tour=:tour WHERE user_id=:user_id",
                   {'tour': _player.tour+1, 'user_id': _player.id})
    conn.commit()

# Прибавляет очко победителю дуэли.
def user_won(_player):
    cursor.execute("UPDATE GameScores SET score=:score WHERE user_id=:user_id",
                   {'score': _player.score+1, 'user_id': _player.id, })
    conn.commit()

# Увеличивает счётчик отыгранных игр у участвующих в дуэли.
def pair_played(_player1, _player2):
    cursor.execute("UPDATE GameScores SET out_of=out_of+1 WHERE user_id=:user_id",
                   {'user_id': _player1.id, })
    cursor.execute("UPDATE GameScores SET out_of=out_of+1 WHERE user_id=:user_id",
                   {'user_id': _player2.id, })
    conn.commit()

# Конвертирует лист участников чата в лист их id.
def users_to_id(participants):
    for i in range(len(participants)):
        yield participants[i].user_id

# Ищет и возвращает игрока по его id в базе данных, в случае необнаружения заносит его в базу данных.
async def get_player_by_id(_id):
    cursor.execute("SELECT name, user_id, score, kicked, tour FROM GameScores WHERE user_id=:user_id", {'user_id': _id})
    result = cursor.fetchall()

    # Если в базе данных нет искомого игрока, он вносится туда.
    if len(result) == 0:
        user = await client.get_entity(await client.get_input_entity(_id))
        name = user.first_name
        score = 0
        cursor.execute("INSERT INTO GameScores VALUES(:name, :user_id, :score, 0, 0, 1)",
                       {'name': name, 'user_id': _id, 'score': score, })
        conn.commit()
        return Player(_id, name, score, 0, 1)
    else:
        return Player(result[0][0], result[0][1], result[0][2], result[0][3], result[0][4])

####
#### Блок асинхронных функций, которые вызываются при срабатывании event listener'ов.
####

# Здесь все входящие сообщения (message) обрабатываются на основании того, в какой чат (peers[peer_index]) они были отправлены.
async def handle_message(message, peer_index):
    # Сообщение заслуживает внимания, только если оно содержит эмоджи-ложку.
    if "🥄" in message.message:
        # Если в чате ведётся дуэль и ложка прислана кем-то из участников дуэли, то:
        if peers[peer_index].pvp_mode_on == True and (message.from_id == peers[peer_index].first_player.id or message.from_id == peers[peer_index].second_player.id):
            # Увеличивается счётчик ложек, "использованных" в ходе дуэли, а id сообщения с ложкой вносится в лист messages_with_spoon_ids, необходимый, если в чате активирована настройка "Удалять сообщения после дуэли".
            peers[peer_index].counter += 1
            peers[peer_index].messages_with_spoon_ids.append(message.id)

            # Генерируется рандомное число от 0 до 100, и если оно меньше вероятности выигрыша в процентах, считается, что автор сообщения с ложкой выигрывает дуэль.
            ran = random.randint(0,100)
            if ran < win_probability_percents:
                winner=None
                loser=None
                spoon=""

                # Согласование слова "ложка" с числительным.
                if peers[peer_index].counter % 10 == 1:
                    spoon=" ложка "
                elif 5 > peers[peer_index].counter % 10 > 1:
                    spoon=" ложки "
                else:
                    spoon=" ложек "

                # Определение победителя и проигравшего.
                if message.from_id == peers[peer_index].first_player:
                    winner = peers[peer_index].first_player
                    loser = peers[peer_index].second_player
                else:
                    winner = peers[peer_index].second_player
                    loser = peers[peer_index].first_player

                # Прибавление 1 очка победителю и увеличение счётчика проведенных дуэлей у обоих игроков.
                user_won(winner)
                pair_played(winner, loser)

                # Если сражение проводилось в рамках турнира, то проигравшего надо исключить из него. Содержание сообщения об окончании дуэли также зависит от этого параметра.
                if peers[peer_index].tournament==True:
                    user_won_tournament(winner)
                    user_kicked_tournament(loser)
                    msg = end_phrases[random.randint(0, len(end_phrases))] + "\n" + winner.name + " : " + str(winner.score) + " +1 (выиграл раунд)\n" + loser.name + " : " + str(
                        loser.score) + " (выбыл из турнира)\n\n" + str(peers[peer_index].counter) + spoon + "было утрачено в процессе битвы."
                else:
                    msg = end_phrases[random.randint(0, len(end_phrases))] + \
                          "\n" + winner.name + " : " + str(winner.score) + " +1\n" + loser.name + " : " + str(loser.score) + "" \
                          "\n\n" + str(peers[peer_index].counter) + spoon + "было утрачено в процессе битвы."

                # Отправка собщения о победе и удаление пользовательских сообщений с ложками (если бота настроили на удаление этих сообщений после дуэли). Обнуление всех параметров пира, связанных с дуэлью.
                await client.send_message(entity=await client.get_input_entity(message.to_id), message=msg,
                                              reply_to=message.id)
                if peers[peer_index].clear_after_duel==True:
                    await  delete_messages(peer_index)
                peers[peer_index].reset()

        # Если сообщение с ложкой прислано вне контекста дуэли и в чате активировано удаление таких сообщений, его следует удалить.
        elif peers[peer_index].delete_immediately==True:
            try:
                await client.delete_messages(await client.get_input_entity(message.to_id), [message.id])
            except Exception as e:
                print(e)


# Ищет команды внутри полученного сообщения и реагирует на каждую команду соответствующим образом.
async def find_command(message, peer_index):
    command=message.message
    if "Вызываю тебя на дуэль!" in message.message or "/call@spoonduelbot" in message.message:
        # Если команда вызова на дуэль была отправлена ответ на чьё-то сообщение:
        if message.reply_to_msg_id is not None:
            replied_message = (await client(GetMessagesRequest(await client.get_input_entity(message.to_id), [message.reply_to_msg_id]))).messages[0]
            to_id = replied_message.from_id

            # Проверка, не вызывал ли пользователь на дуэль сам себя.
            if to_id != message.from_id:
                reply_markup = ReplyInlineMarkup([KeyboardButtonRow([KeyboardButtonCallback(text="❤️️", data=str(to_id)), KeyboardButtonCallback(text="💔", data=b'0')])]) # create
                await client.send_message(entity=await client.get_input_entity(message.to_id), message = "[Ты](tg://user?id="+str(to_id)+") "+begin_phrase, reply_to = message.id, buttons = reply_markup)
        # Если вызов был отправлен в пустоту, не в ответ на чье-то сообщение, бот раздраженно отправит пользователя читать инструкцию.
        else:
            await client.send_message(entity=await client.get_input_entity(message.to_id), message=annoyed_reply, reply_to=message.id)
    elif "/showstats@spoonduelbot" in command:
        # Извлечение информации о всех пользователях из базы данных.
        cursor.execute("SELECT * FROM GameScores ORDER BY score DESC")
        result = cursor.fetchall()

        # Запрос на получение первых 100000 участников чата (то есть среднестатистически - всех) и конвертирование результатов запроса в лист из id участников.
        members = await client(GetParticipantsRequest(channel = await client.get_input_entity(message.to_id), filter = ChannelParticipantsSearch(''), offset = 0, limit = 100000, hash = 0))
        ids = list(users_to_id(members.participants))

        # Перебор всех игроков из базы данных (results) и проверка на наличие каждого в чате (ids). Перебор заканчивается при обнаружении первых 10 игроков, удовлетворяющих условию.
        msg = "**Боги рандома:**\n"
        counter=0
        for i in result:
            if i[1] in ids:
                msg += "**" + str(i[2]) + "** у " + str(i[0]) + "\n"
                counter+=1
                if counter==10:
                    break
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = msg, reply_to = message.id)
    elif "/luckiest@spoonduelbot" in command: # in this ELIF block the bot shows current stats
        # Извлечение информации о всех пользователях из базы данных.
        cursor.execute("SELECT * FROM GameScores ORDER BY score DESC")
        result = cursor.fetchall()

        # Запрос на получение первых 100000 участников чата (то есть среднестатистически - всех) и конвертирование результатов запроса в лист из id участников.
        members = await client(GetParticipantsRequest(channel = await client.get_input_entity(message.to_id), filter = ChannelParticipantsSearch(''), offset = 0, limit = 100000, hash = 0))
        ids = list(users_to_id(members.participants))

        # Перебор всех игроков из базы данных (results) и проверка на наличие каждого в чате (ids). Перебор заканчивается при обнаружении первых 10 игроков, удовлетворяющих условию.
        msg = "**Переигравшие удачу** (отношение побед/битв):\n"
        counter=0
        for i in result:
            if i[1] in ids:
                msg += "**" + str(round(float(i[2])/float(i[3]) if i[3]!=0 else 0, 2)) + "** у " + str(i[0]) + "\n"
                if counter==10:
                    break
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = msg, reply_to = message.id)
    elif "/help@spoonduelbot" in command:
        # Отправка help-сообщения.
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = help_message, reply_to = message.id)
    elif "/tournament@spoonduelbot" in command:
        # Извлечение информации о всех пользователях из базы данных.
        cursor.execute("SELECT * FROM GameScores WHERE kicked=0 ORDER BY tour DESC")
        result = cursor.fetchall()

        # Запрос на получение первых 100000 участников чата (то есть среднестатистически - всех) и конвертирование результатов запроса в лист из id участников.
        members = await client(GetParticipantsRequest(channel = await client.get_input_entity(message.to_id), filter = ChannelParticipantsSearch(''), offset = 0, limit = 100000, hash = 0))
        ids = list(users_to_id(members.participants))

        # Перебор всех игроков из базы данных (results) и проверка на наличие каждого в чате (ids). Перебор заканчивается при обнаружении первых 10 игроков, удовлетворяющих условию.
        msg = "**Статистика текущего турнира:**\n"
        counter=0
        for i in result:
            if i[1] in ids:
                msg += "**" + str(i[5]) + "** раунд: " + str(i[0]) + "\n"
                counter+=1
                if counter==10:
                    break
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = text, reply_to = message.id)
    elif "/preferences@spoonduelbot" in command:
        # Отправка сообщения с настройками.
        reply_markup = ReplyInlineMarkup([
            KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять сразу" if peers[peer_index].delete_immediately == False else "Не удалять сразу"), data=b"di_switch")]),
            KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять после дуэли" if peers[peer_index].clear_after_duel == False else "Не удалять после дуэли"), data=b"ca_switch")]),
            KeyboardButtonRow([KeyboardButtonCallback(text="❌Удалить это сообщение❌", data=b"del_message")])])
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = preferences_message, buttons = reply_markup, reply_to = message.id)


####
#### Эта функция обеспечивает здоровую реакцию бота на нажатие кнопок в тех его сообщениях, в которых имеются кнопки.
####


async def handle_query(event, peer_index):
    # Для работы с query нужно знать id вызывающего на дуэль (caller_id), id вызванного на дуэль (called_id) и id вызвавшего query (query_sender_id) пользователей. Первые два параметра необходимы только в том случае, если кнопка прикреплена к сообщению с вызовом на дуэль.
    chat = await client.get_input_entity(event.query.peer)

    bot_message = (await client(GetMessagesRequest(chat, [event.query.msg_id]))).messages[0]

    try:
        caller_message = (await client(GetMessagesRequest(chat, [bot_message.reply_to_msg_id]))).messages[0]
        caller_id = caller_message.from_id

        called_message = (await client(GetMessagesRequest(chat, [caller_message.reply_to_msg_id]))).messages[0]
        called_id = called_message.from_id
    except Exception as e:
        print(e)
        print("Error: there is no one called on the Duel!")

    query_sender_id = event.query.user_id

    # Случай, когда кнопка - переключатель настройки удаления всех сообщений с ложкой, отправленных вне контекста дуэли.
    if event.query.data==b'di_switch':
        query_sender = await client(GetParticipantRequest(chat, await client.get_input_entity(query_sender_id)))

        # Проверка, явялется ли нажавший на кнопку администратором или создателем чата.
        if isinstance(query_sender.participant, ChannelParticipantAdmin) or isinstance(query_sender.participant, ChannelParticipantCreator):
            # Изменение соответствующего параметра данного чата в листе пиров.
            peers[peer_index].delete_immediately = not peers[peer_index].delete_immediately

            # Обновление панели с кнопками в сообщении.
            reply_markup = ReplyInlineMarkup([
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять сразу" if peers[peer_index].delete_immediately == False else "Не удалять сразу"), data=b"di_switch")]),
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять после дуэли" if peers[peer_index].clear_after_duel == False else "Не удалять после дуэли"), data=b"ca_switch")]),
            KeyboardButtonRow([KeyboardButtonCallback(text="❌Удалить сообщение❌", data=b"del_message")])])
            await client.edit_message(entity= chat, message = event.query.msg_id, text = preferences_message, buttons = reply_markup)

            # Изменение базы данных.
            cursor.execute("UPDATE ChatsPreferences SET delete_immediately=:delete_immediately WHERE chat_id=:chat_id", {'delete_immediately':peers[peer_index].delete_immediately,'chat_id':peers[peer_index].id})
            conn.commit()
            await client(SetBotCallbackAnswerRequest(query_id=event.query.query_id, cache_time=1, message="Настройки успешно изменены."))
        # Если нажавший на кнопку - рядовой пользователь, он информируется об отсутствии прав для изменения настроек.
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 1, message = "Простите, у вас недостаточно прав."))

    # Случай, когда кнопка - переключатель настройки удаления сообщений с ложкой после дуэли.
    elif event.query.data==b'ca_switch':
        query_sender = await client(GetParticipantRequest(chat, await client.get_input_entity(query_sender_id)))

        # Проверка, явялется ли нажавший на кнопку администратором или создателем чата.
        if isinstance(query_sender.participant, ChannelParticipantAdmin) or isinstance(query_sender.participant, ChannelParticipantCreator):
            # Изменение соответствующего параметра данного чата в листе пиров.
            peers[peer_index].clear_after_duel = not peers[peer_index].clear_after_duel

            # Изменение соответствующего параметра данного чата в листе пиров.
            reply_markup = ReplyInlineMarkup([
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять сразу" if peers[peer_index].delete_immediately == False else "Не удалять сразу"), data=b"di_switch")]),
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять после дуэли" if peers[peer_index].clear_after_duel == False else "Не удалять после дуэли"), data=b"ca_switch")]),
                 KeyboardButtonRow([KeyboardButtonCallback(text="❌Удалить сообщение❌", data=b"del_message")])])
            await client.edit_message(entity= chat, message = event.query.msg_id, text = preferences_message, buttons = reply_markup)

            # Изменение базы данных.
            cursor.execute("UPDATE ChatsPreferences SET clear_after_duel=:clear_after_duel WHERE chat_id=:chat_id", {'clear_after_duel':peers[peer_index].clear_after_duel,'chat_id':peers[peer_index].id})
            conn.commit()
            await client(SetBotCallbackAnswerRequest(query_id=event.query.query_id, cache_time=1, message="Настройки успешно изменены."))
            # Если нажавший на кнопку - рядовой пользователь, он информируется об отсутствии прав для изменения настроек.
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 1, message = "Простите, у вас недостаточно прав."))

    # Случай, когда кнопка - удаление сообщения с настройками.
    elif event.query.data==b'del_message':
        query_sender = await client(GetParticipantRequest(chat, await client.get_input_entity(query_sender_id)))

        # Если нажавший на кнопку является администратором или создателем чата, сообщение удаляется.
        if isinstance(query_sender.participant, ChannelParticipantAdmin) or isinstance(query_sender.participant, ChannelParticipantCreator):
            await client.delete_messages(chat, event.query.msg_id)
        # Иначе он уведомляется об отсутствии прав на удаление сообщения.
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 42, message = "Простите, у вас недостаточно прав."))

    # Случай, когда кнопка - отклонение приглашения на дуэль.
    elif event.query.data==b'0':
        # Проверка, является ли нажавщий на кнопку отправителем приглашения или приглашённым.
        if called_id == query_sender_id or caller_id == query_sender_id:
            await client.edit_message(entity=chat, message = event.query.msg_id, text = markdown.unparse(bot_message.message, bot_message.entities) + "\n\nВызов был аннулирован.")
        # Коль скоро он им не является, он уведомляется об отсутствии прав на отклонение приглашения.
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 42, message = "Простите, вы не можете аннулировать этот вызов."))

    # Случай, когда кнопка - принятие вызова на дуэль.
    else:
        # Проверка, не идёт ли сейчас в этом чате другая дуэль и не превысила ли её длительность пороговое значение.
        if peers[peer_index].pvp_mode_on == False or time.time()-peers[peer_index].time_when_duel_started>time_limit:
            # Проверка id, зашитого в кнопку, на совпадение с id нажавшего на кнопку пользователя.
            if query_sender_id == int(event.query.data.decode('ascii')):
                # Создание объектов класса peer, представляющих двух участников дуэли.
                peers[peer_index].input_peer = chat
                peers[peer_index].first_player = await get_player_by_id(caller_id)
                peers[peer_index].second_player = await get_player_by_id(called_id)

                # Текст (msg), добавляемый к исходному сообщению, зависит от того, потребовалось ли прекратить предыдущую дуэль для начала нынешней.
                msg = markdown.unparse(bot_message.message, bot_message.entities) + "\n\nВызов был принят."
                if peers[peer_index].first_player.kicked == 0 and peers[peer_index].second_player.kicked == 0 and peers[peer_index].first_player.tour==peers[peer_index].second_player.tour:# check if both players are capable of participating in the Tournament
                    peers[peer_index].tournament = True
                    msg += "\n\n**Вы участвуете в турнире, раунд** " + str(peers[peer_index].first_player.tour) # second part of the message
                if peers[peer_index].time_when_duel_started is not None and time.time()-peers[peer_index].time_when_duel_started>time_limit:
                    msg+="\n\n__Предыдущая дуэль в этом чате была остановлена ввиду превышения лимита времени.__"
                await client.edit_message(entity = chat, message = event.query.msg_id, text = msg)

                # Включается индикатор наличия в чате активной дуэли и установление времени её начала. Если дуэль будет длиться дольше порогового значения, бот имеет право прекратить её и начать другую.
                peers[peer_index].pvp_mode_on = True
                peers[peer_index].time_when_duel_started=time.time()
            # Если id, вшитое в кнопку, и id нажавшего на кнопку пользователя не совпадают, нажавший уведомляется о том, что вызов бросили не ему.
            else:
                await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 42, message = "Простите, вызов был брошен не вам."))
        # Пока в этом чате ведётся дуэль, длительность которой пока не превысила пороговое значение, новую дуэль начать невозможно.
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 42, message = "Простите, в данный момент дуэль уже ведётся."))


####
#### Сейчас произойдёт инициация всех необходимых констант, объявление event listener'ов и запуск самого клиента.
####

init()


# Срабатывает при каждом новом входящем сообщении.
@client.on(events.NewMessage())
async def handlerNewMessage(event):
    # Получение индекса пира, в который пришло сообщение.
    id = list(event.message.to_id.__dict__.values())[0]
    index = await get_peer_index_by_id(id)

    # Поиск команд в сообщении
    try:
        await find_command(event.message, index)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)

    # Обработка сообщения (если оно содержит ложку-эмодзи)
    try:
        await handle_message(event.message, index)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)

# Срабатывает при каждом нажатии любой кнопки.
@client.on(events.CallbackQuery())
async def handlerCallbackQuery(event):
    index = await get_peer_index_by_id(list(event.query.peer.__dict__.values())[0])
    try:
        await handle_query(event, index)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)

# Срабатывает при получении callback-a в инлайн-режиме.
@client.on(events.InlineQuery())
async def handlerInlineQuery(event):
    await client(SetInlineBotResultsRequest(query_id=event.query.query_id, cache_time=42, results=[
            InputBotInlineResult(id="1", type="article", title="Кинуть ложкой в собеседника!", description = "Очень пригодится, если не можете найти ложку на панели с эмоджи.",
                                         send_message=InputBotInlineMessageText("🥄"),
                                         thumb=InputWebDocument(url="https://www.crosbys.co.uk/images/products/medium/1441875843-88708300.jpg",
                                                                        size=42,mime_type="image/jpeg",
                                                                        attributes=[DocumentAttributeImageSize(
                                                                            w=42,
                                                                            h=42
                                                                        )]
                                                                        ))
    ]))


client.start()
client.run_until_disconnected()
conn.close()