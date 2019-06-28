from globals import *
from classes import *


def init():
    global API_ID
    global API_HASH
    global BOT_TOKEN
    global client
    global conn
    global cursor
    config = configparser.ConfigParser()
    print(os.path.join(os.path.dirname(__file__), 'config.ini'))
    config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))
    if config.has_section('API') == False:
        print("Creating a new .ini file...")
        config.add_section('API')
        id_input = input("Please enter your API's id: ")
        hash_input = input("Please enter your API's hash: ")
        bot_token_input = input("Please enter your bot's token: ")
        config.set('API', 'id', id_input)
        config.set('API', 'hash', hash_input)
        config.set('API', 'token', bot_token_input)
        print("Writing config.ini...")
        config.write(open(os.path.join(os.path.dirname(__file__), 'config.ini'), 'w'))
    API_ID = config.getint('API', 'id')
    API_HASH = config.get('API', 'hash')
    BOT_TOKEN = config.get('API', 'token')
    client = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    conn = sqlite3.connect('gamelogs.sqlite', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS GameScores('name' INTEGER, 'user_id' INTEGER, 'score' INTEGER, 'kicked' INTEGER DEFAULT 0, 'tour' INTEGER DEFAULT 1)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ChatsPreferences( 'chat_id' INTEGER, 'chat_name' TEXT, 'delete_immediately' INTEGER, 'clear_after_duel' INTEGER)")
    cursor.execute("SELECT * FROM ChatsPreferences")
    chats_from_table = cursor.fetchall()
    for chat_from_table in chats_from_table:
        new_peer = Peer(*chat_from_table) # initialize new Peer by id
        peers.append(new_peer)
    print(chats_from_table)


async def get_peer_index_by_id(_id):
    for i in range(len(peers)):
        if peers[i].id == _id:
            print(i)
            print(len(peers))
            return i
    chat = await client.get_entity(await client.get_entity(_id))
    cursor.execute("INSERT INTO ChatsPreferences VALUES(:id, :name, 0, 0)", {'id':chat.id, 'name':chat.title})
    conn.commit()
    peers.append(Peer(chat.id, chat.title, 0, 0))
    return len(peers)-1


async def delete_messages(peer_index):
    try:  # handle some unforeseen exceptions which still may occur
        res = await client.delete_messages(peers[peer_index].input_peer, peers[peer_index].messages_with_spoon_ids)
        peers[peer_index].messages_with_spoon_ids = []
    except Exception as e:
        print(e)

def user_kicked_tournament(_player):
    cursor.execute("UPDATE GameScores SET kicked=1, tour=0 WHERE user_id=:user_id",
                   {'user_id': _player.id})
    conn.commit()

def user_won_tournament(_player):
    cursor.execute("UPDATE GameScores SET tour=:tour WHERE user_id=:user_id",
                   {'tour': _player.tour+1, 'user_id': _player.id})
    conn.commit()

def user_won(_player):
    cursor.execute("UPDATE GameScores SET score=:score WHERE user_id=:user_id",
                   {'score': _player.score+1, 'user_id': _player.id, })
    conn.commit()

#def reset_peer():

async def handle_message(message, peer_index):
    if "🥄" in message.message: # if the bot finds at least 1 SPOON emoji in the message...
        if peers[peer_index].pvp_mode_on == True and (message.from_id == peers[peer_index].first_player.id or message.from_id == peers[peer_index].second_player.id): # if there is an active Duel...
            print(peers[peer_index].pvp_mode_on, message.from_id == peers[peer_index].first_player, message.from_id == peers[peer_index].second_player)
            peers[peer_index].counter += 1
            peers[peer_index].messages_with_spoon_ids.append(message.id)
            ran = random.randint(0,100) # then the "dice" is "thrown"
            print(ran)
            if ran < win_probability_percents:
                winner=None
                loser=None
                spoon=""
                if peers[peer_index].counter % 10 == 1:
                    spoon=" ложка "
                elif 5 > peers[peer_index].counter % 10 > 1:
                    spoon=" ложки "
                else:
                    spoon=" ложек "
                if message.from_id == peers[peer_index].first_player:
                    winner = peers[peer_index].first_player
                    loser = peers[peer_index].second_player
                else:
                    winner = peers[peer_index].second_player
                    loser = peers[peer_index].first_player
                user_won(winner)
                if peers[peer_index].tournament==True:
                    user_won_tournament(winner)
                    user_kicked_tournament(loser)
                    msg = end_phrases[random.randint(0, len(end_phrases))] + "\n" + winner.name + " : " + str(winner.score) + " +1 (выиграл раунд)\n" + loser.name + " : " + str(
                        loser.score) + " (выбыл из турнира)\n\n" + str(peers[peer_index].counter) + spoon + "было утрачено в процессе битвы."
                    await client.send_message(entity=await client.get_input_entity(message.to_id), message=msg,
                                              reply_to=message.id)
                else:
                    msg = end_phrases[random.randint(0, len(end_phrases))] + \
                          "\n" + winner.name + " : " + str(winner.score) + " +1\n" + loser.name + " : " + str(loser.score) + "" \
                          "\n\n" + str(peers[peer_index].counter) + spoon + "было утрачено в процессе битвы."
                    await client.send_message(entity=await client.get_input_entity(message.to_id), message=msg,
                                              reply_to=message.id)
                if peers[peer_index].clear_after_duel==True:
                    await  delete_messages(peer_index)
                peers[peer_index].reset()
        elif peers[peer_index].delete_immediately==True: # if the bot is an admin of the chat, he will delete all messages with a SPOON emoji so as to prevent flood
            try: # handle some unforeseen exceptions which still may occur
                await client.delete_messages(await client.get_input_entity(message.to_id), [message.id])
            except Exception as e:
                print(e)

def users_to_id(participants):
    for i in range(len(participants)):
        yield participants[i].user_id

async def get_player_by_id(_id):
    cursor.execute("SELECT name, user_id, score, kicked, tour FROM GameScores WHERE user_id=:user_id", {'user_id': _id})
    result = cursor.fetchall()
    if len(result) == 0:  # if the caller is not found on our .sqlite table, we should insert his data in it
        user = await client.get_entity(await client.get_input_entity(_id))
        name = user.first_name
        score = 0
        cursor.execute("INSERT INTO GameScores VALUES(:name, :user_id, :score, 0, 1)",
                       {'name': name, 'user_id': _id, 'score': score, })
        conn.commit()  # commit all the changes done to the database!!!!!!!!
        return Player(_id, name, score, 0, 1)
    else:  # if we successfully fetched all his/her data from the table...
        print(result[0])
        return Player(result[0][0], result[0][1], result[0][2], result[0][3], result[0][4])

async def find_command(message, peer_index):
    command=message.message
    print("!")
    if "Вызываю тебя на дуэль!" in command or "/call@spoonduelbot" in command:
        if message.reply_to_msg_id is not None:
            reply_to_messages = await client(GetMessagesRequest(await client.get_input_entity(message.to_id), [message.reply_to_msg_id]))
            toID = reply_to_messages.messages[0].from_id
            if toID != message.from_id: # prevents users from calling themselves on a Duel! (would be easy to earn higher scores)
                replMarkup = ReplyInlineMarkup([KeyboardButtonRow([KeyboardButtonCallback(text="❤️️", data=str(toID)), KeyboardButtonCallback(text="💔", data=b'0')])]) # create
                await client.send_message(entity=await client.get_input_entity(message.to_id), message = "[Ты](tg://user?id="+str(toID)+") "+begin_phrase, reply_to = message.id, buttons = replMarkup)
        else:
            await client.send_message(entity=await client.get_input_entity(message.to_id), message=annoyed_reply, reply_to=message.id)

    elif "/showstats@spoonduelbot" in command: # in this ELIF block the bot shows current stats
        cursor.execute("SELECT * FROM GameScores ORDER BY score DESC")
        result = cursor.fetchall()
        members = await client(GetParticipantsRequest(channel = await client.get_input_entity(message.to_id), filter = ChannelParticipantsSearch(''), offset = 0, limit = 100000, hash = 0))
        ids = list(users_to_id(members.participants))
        text = "БОГИ РАНДОМА (длина ложки в см)\n"
        for i in result:
            if i[1] in ids:
                text += str(i[2]) + " у " + str(i[0]) + "\n"
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = text, reply_to = message.id)
    elif "/help@spoonduelbot" in command: # in this ELIF block the bot sends a help message
        print(repr(help_message))
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = help_message, reply_to = message.id)
    elif "/tournament@spoonduelbot" in command: # in this ELIF block the bot shows current Tournament stats
        cursor.execute("SELECT * FROM GameScores WHERE kicked=0 ORDER BY tour DESC")
        result = cursor.fetchall()
        counter = 20
        members = await client(GetParticipantsRequest(channel = await client.get_input_entity(message.to_id), filter = ChannelParticipantsSearch(''), offset = 0, limit = 100000, hash = 0))
        ids = list(users_to_id(members.participants))
        text = "ТЕКУЩИЙ ТУРНИР\n"
        ent = [MessageEntityBold(offset = 0, length = len(text))]
        length = len(text)
        for i in result:
            if i[1] in ids:
                ent.append(MessageEntityBold(offset = length, length = len(str(i[4]))))
                text += str(i[4]) + " раунд: " + str(i[0]) + "\n"
                counter-=1
                length = length + 9 + len(str(i[4])) + len(str(i[0]))
                if counter == 0:
                    break
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = text, reply_to = message.id)
    elif "/preferences@spoonduelbot" in command:
        replMarkup = ReplyInlineMarkup([
            KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять сразу" if peers[peer_index].delete_immediately == False else "Не удалять сразу"), data=b"di_switch")]),
            KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять после дуэли" if peers[peer_index].clear_after_duel == False else "Не удалять после дуэли"), data=b"ca_switch")]),
            KeyboardButtonRow([KeyboardButtonCallback(text="❌Удалить это сообщение❌", data=b"del_message")])])
        await client.send_message(entity=await client.get_input_entity(message.to_id), message = preferences_message, buttons = replMarkup, reply_to = message.id)
        print("settings")
    elif "/sendimage@spoonduelbot" in command:
        urls = test_google.google("spoon", 10)
        index = random.randint(0, len(urls)-1)

        img = test_google.Image.open(test_google.requests.get(urls[index], stream=True).raw)
        img.save('img1.jpg')
        await client.send_file(await client.get_input_entity(message.to_id), 'img1.jpg')

async def handle_query(event, peer_index):
    # the chat where the bot's message has been sent to
    chat = await client.get_input_entity(event.query.peer)

    # regrettably, the GetMessagesRequest returns some other stuff besides of a list of the requested messages,
    # therefore it will be more comprehensible to split in two parts the process of getting the message
    bot_messages = await client(GetMessagesRequest(chat, [event.query.msg_id]))
    bot_message = bot_messages.messages[0]

    # same story here;
    # the caller is someone who called somebody else on a Duel
    caller_messages = await client(GetMessagesRequest(chat, [bot_message.reply_to_msg_id]))
    caller_message = caller_messages.messages[0]
    caller_id = caller_message.from_id

    # same;
    # the called is someone who is called on a Duel by the caller
    try:
        called_messages = await client(GetMessagesRequest(chat, [caller_message.reply_to_msg_id]))
        called_message = called_messages.messages[0]
        called_id = called_message.from_id
    except Exception as e:
        print(e)
        print("Error: there is no one called on the Duel!")

    # the query sender is someone who has pressed a button and therefore has sent a query to the bot
    query_sender_id = event.query.user_id
    if event.query.data==b'di_switch':
        query_sender = await client(GetParticipantRequest(chat, await client.get_input_entity(query_sender_id)))
        if isinstance(query_sender.participant, ChannelParticipantAdmin) or isinstance(query_sender.participant, ChannelParticipantCreator):
            peers[peer_index].delete_immediately = not peers[peer_index].delete_immediately
            replMarkup = ReplyInlineMarkup([
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять сразу" if peers[peer_index].delete_immediately == False else "Не удалять сразу"), data=b"di_switch")]),
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять после дуэли" if peers[peer_index].clear_after_duel == False else "Не удалять после дуэли"), data=b"ca_switch")]),
            KeyboardButtonRow([KeyboardButtonCallback(text="❌Удалить сообщение❌", data=b"del_message")])])
            await client.edit_message(entity= chat, message = event.query.msg_id, text = preferences_message, buttons = replMarkup)
            cursor.execute("UPDATE ChatsPreferences SET delete_immediately=:delete_immediately WHERE chat_id=:chat_id", {'delete_immediately':peers[peer_index].delete_immediately,'chat_id':peers[peer_index].id})
            conn.commit()
            await client(SetBotCallbackAnswerRequest(query_id=event.query.query_id, cache_time=1, message="Настройки успешно изменены."))
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 1, message = "Простите, у вас недостаточно прав."))
    elif event.query.data==b'ca_switch':
        print("asdkk")
        query_sender = await client(GetParticipantRequest(chat, await client.get_input_entity(query_sender_id)))
        if isinstance(query_sender.participant, ChannelParticipantAdmin) or isinstance(query_sender.participant, ChannelParticipantCreator):
            peers[peer_index].clear_after_duel = not peers[peer_index].clear_after_duel
            replMarkup = ReplyInlineMarkup([
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять сразу" if peers[peer_index].delete_immediately == False else "Не удалять сразу"), data=b"di_switch")]),
                 KeyboardButtonRow([KeyboardButtonCallback(text=("Удалять после дуэли" if peers[peer_index].clear_after_duel == False else "Не удалять после дуэли"), data=b"ca_switch")]),
                 KeyboardButtonRow([KeyboardButtonCallback(text="❌Удалить сообщение❌", data=b"del_message")])])
            await client.edit_message(entity= chat, message = event.query.msg_id, text = preferences_message, buttons = replMarkup)
            cursor.execute("UPDATE ChatsPreferences SET clear_after_duel=:clear_after_duel WHERE chat_id=:chat_id", {'clear_after_duel':peers[peer_index].clear_after_duel,'chat_id':peers[peer_index].id})
            conn.commit()
            await client(SetBotCallbackAnswerRequest(query_id=event.query.query_id, cache_time=1, message="Настройки успешно изменены."))
            print("фывждл")
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 1, message = "Простите, у вас недостаточно прав."))
    elif event.query.data==b'del_message':
        query_sender = await client(GetParticipantRequest(chat, await client.get_input_entity(query_sender_id)))
        if isinstance(query_sender.participant, ChannelParticipantAdmin) or isinstance(query_sender.participant, ChannelParticipantCreator):
            await client.delete_messages(chat, event.query.msg_id)
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 1, message = "Простите, у вас недостаточно прав."))
    elif event.query.data==b'0': # means that the query sender has pressed a button to decline a Duel
        if called_id == query_sender_id or caller_id == query_sender_id: # nobody besides of the caller and the called can decline the Duel!
            await client.edit_message(entity=chat, message = event.query.msg_id, text = bot_message.text + "\n\nВызов был аннулирован.")
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 1, message = "Простите, вы не можете аннулировать этот вызов."))
    else:
        if peers[peer_index].pvp_mode_on == False or time.time()-peers[peer_index].time_when_duel_started>time_limit:  # if there's no Duel which takes place right now
            if query_sender_id == int(event.query.data.decode('ascii')):  # check if the query sender is the called one
                peers[peer_index].input_peer = chat
                peers[peer_index].first_player = await get_player_by_id(caller_id)
                peers[peer_index].second_player = await get_player_by_id(called_id)
                msg = markdown.unparse(bot_message.message, bot_message.entities) + "\n\nВызов был принят."
                if peers[peer_index].first_player.kicked == 0 and peers[peer_index].second_player.kicked == 0 and peers[peer_index].first_player.tour==peers[peer_index].second_player.tour:# check if both players are capable of participating in the Tournament
                    peers[peer_index].tournament = True
                    msg += "\n\n**Вы участвуете в турнире, раунд** " + str(peers[peer_index].first_player_tour) # second part of the message
                if peers[peer_index].time_when_duel_started is not None and time.time()-peers[peer_index].time_when_duel_started>time_limit:
                    msg+="\n\n__Предыдущая дуэль в этом чате была остановлена ввиду превышения лимита времени.__"
                await client.edit_message(entity = chat, message = event.query.msg_id, text = msg)
                peers[peer_index].pvp_mode_on = True
                peers[peer_index].time_when_duel_started=time.time()
            else:
                await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 42, message = "Простите, вызов был брошен не вам."))
        else:
            await client(SetBotCallbackAnswerRequest(query_id = event.query.query_id, cache_time = 42, message = "Простите, в данный момент дуэль уже ведётся."))


init()

@client.on(events.Raw())
async def handlerRaw(event):
    print(event)
    print("!!!!!!!!!!!!!!!!")

@client.on(events.NewMessage())
async def handlerNewMessage(event):
    id = list(event.message.to_id.__dict__.values())[0]
    index = await get_peer_index_by_id(id)
    try:
        await find_command(event.message, index)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)
    try:
        await handle_message(event.message, index)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)


@client.on(events.CallbackQuery())
async def handlerCallbackQuery(event):
    print(event)
    print(list(event.query.__dict__.values())[0])
    index = await get_peer_index_by_id(list(event.query.peer.__dict__.values())[0])
    print(index)
    try:
        await handle_query(event, index)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)

@client.on(events.InlineQuery())
async def handlerInlineQuery(event):
    res = await client(SetInlineBotResultsRequest(query_id=event.query.query_id, cache_time=42, results=[
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
    print(res)


@client.on(events.ChatAction())  # here all cases when any button is pressed are handled
async def handlerChatAction(event):
    print(event)

client.start()
client.run_until_disconnected()
conn.close()