# import pyximport; pyximport.install()

from GameLogic import Reversi, NOBODY, player_name
from worker import Locking, WorkerThreadServer
from utils import is_mobile


class Controller(Locking):
    def __init__(self, board_size, dispatch, scheduler, log):
        super().__init__()
        self.__replay = None
        self.__before_replay = None # (board, turn, undo)
        self.__dispatch = dispatch
        self.__scheduler = scheduler
        self.__work = WorkerThreadServer()
        self.__game = Reversi(board_size, self.__work.post, log)        
        self.__state = {}
        self.update_state()

    def accepting_input(self):
        return not self.is_replay()
        
    def dispatch_messages(self, *_):
        for msg, args in self.__work.messages():
            if msg is None:
                continue            
            if msg == 'cannot_move':
                args = (player_name(*args),)
            self.__dispatch(msg, args)

    @property
    @Locking.synchronized
    def state(self):
        return self.__state.copy()

    @Locking.synchronized
    def set_state(self, new_state):
        old_state = self.__state
        self.__state = new_state
        return old_state

    @state.setter
    def state(self, new_state):
        self.set_state(new_state)
   
    ''' wrap func in update calls '''
    def send_message(self, func):
        self.update_state()
        self.__work.send_message(func)
        self.__work.send_message(self.update_state)

    @property
    def board_size(self):
        return self.__game.dim

    @property
    def board_state(self):
        return self.__game.state()

    def is_replay(self):
        return self.__before_replay != None

    @property
    def last_move_coords(self):
        return self.__game.board.last_move()

    def move(self, row, col):
        if self.accepting_input():
            self.__game.do_user_move(row, col)

    def next(self, *_):
        if self.is_replay():
            self.schedule_once(self.__replay_next, .5)
        else:
            self.send_message(self.__game.do_machine_move)

    def new_game(self):
        def start_new_game(*_):
            self.__game.new_game()
            self.__work.post('ready')
        self.send_message(start_new_game)

    def owner(self, row, col):
        return self.__game.board.owner(row, col)

    def replay(self, *_):
        self.__work.pause() # pause the AI
        self.__replay = self.__game.board.playLog.copy()
        self.__before_replay = (self.__game.board, self.__game.turn, self.__game.undo)
        self.__game.new_game()
        self.update_state()
        self.schedule_once(self.__replay_next, 1)

    def __replay_next(self):
        if self.__replay:
            player, move = self.__replay[0]
            self.__replay = self.__replay[1:]
            self.__game.play_with_undo(player, move, undo=False, update=True)
        elif self.__before_replay:
            if self.__work.resume():
                self.send_message(self.__replay_cancelled)

    def schedule_once(self, what, delay):
        self.__scheduler(lambda *_: what(), delay)

    def touch(self):
        if self.is_replay():
            self.__replay = None # cancel it

    def quit(self):
        self.__work.stop()

    def switch(self):
        self.send_message(self.__game.switch)

    def undo(self):
        self.send_message(self.__game.undo_turn)
        
    def update_state(self):
        replay = bool(self.__replay)
        game_over = self.__game.is_game_over()
        busy = not game_over and not replay and self.__game.turn==self.__game.player
        working = busy or replay
        state = {
            'ai_busy': busy,
            'replay': replay,
            'game_over': game_over,
            'can_new':  not working and not self.__game.is_new_game(),
            'can_replay': not working and self.__game.can_undo(),
            'can_switch': not working and not game_over,
            'can_undo': not working and self.__game.can_undo(),
        }
        state = self.set_state(state)
        if game_over and not state['game_over']:
            self.__work.post('game_over', *self.__game.board.score)
        else:
            self.__work.post('update')

    def status_info(self):
        state = self.state
        if state['ai_busy']:
            info = 'Thinking...'
        elif state['game_over'] and not state['replay']:
            winner = 'NOBODY'
            score = self.__game.board.score
            if score[0] > score[1]:
                winner =  player_name(0)
            elif score[0] < score[1]:
                winner =  player_name(1)
            info = 'Game over: {} won.'.format(winner)                
        else:
            turn = self.__game.turn
            if self.state['replay']:
                info = ('Touch' if is_mobile() else 'Click') + ' anyhere to cancel replay'
            else:
                who = 'Machine\'s' if self.__game.player==turn else 'Your'
                info = '{} turn ({})'.format(who, player_name(turn))
        return info

    @staticmethod
    def is_nobody(player):
        return player == NOBODY

    @staticmethod
    def format_score(score):
        return '{}: {}, {}: {}'.format(player_name(0), score[0], player_name(1), score[1])
    
    @staticmethod
    def set_player_names(names):
        Reversi.set_player_names(names)

    def machine_player_name(self):
        return player_name(self.__game.player)

    def __replay_cancelled(self):
        self.__game.board, self.__game.turn, self.__game.undo = self.__before_replay
        self.__before_replay = None

    @property
    def game_data(self):
        return {
            'game': self.__game.board.playLog,
            'turn': self.__game.turn,
            'machine': self.__game.player
        }

    @game_data.setter
    def game_data(self, data):
        if not data:
            return
        self.__game.turn = turn = data['turn']
        self.__game.player = data['machine']
        self.__game.replay_log(data['game'])
