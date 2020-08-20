#import pyximport; pyximport.install()
from kivy.config import Config

Config.set('graphics', 'resizable', False)
Config.set('graphics', 'multisamples', 8)

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.logger import Logger
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.storage.dictstore import DictStore

from GameLogic import int_to_bits
from collections import deque
from controller import Controller
from msgbox import MessageBox
from utils import is_mobile

from os import path, walk
import json

VERSION = 'Tableau\'s {} 1.0'
DATA_DIR = 'data'


class ThemeManager:
    @staticmethod
    def load(dir=None):
        name = dir = dir or 'Tableau'
        dir = path.join(DATA_DIR, dir)
        with open(path.join(dir, 'theme.json'), 'r') as f:
            theme = type('Theme', (object, ), json.load(f))
            Controller.set_player_names(theme.names)
        theme.texture = [ Image(path.join(dir, i), mipmap=True).texture for i in theme.texture ]
        if theme.background:
             theme.background = path.join(dir, theme.background)
        theme.name = name
        Window.set_title(theme.title)
        return theme

    @staticmethod
    def icon():
        return path.join(DATA_DIR, 'icon.png')


class BoardWidget(Widget):
    ''' Game board widget '''
    def __init__(self, controller, log_callback, **args):
        super().__init__(**args)
        self.theme = ThemeManager.load()
        self.controller = controller
        self.log = log_callback
        self.margin = [5, 5]
        self.bind(pos=self.on_update)
        self.bind(size=self.on_update)        
        self.current_animation = {}
        self.once = 2
        self.update = Clock.create_trigger(self.on_update)
        self.last_move = None
        self.modal = None        

    def cell_size(self):
        return self.grid_size() / self.dim

    @property
    def dim(self):
        return self.controller.board_size

    def message_box(self, title, text, on_close=None):
        if not self.modal:
            open = not self.current_animation
            self.modal = MessageBox(title, text, size=(450, 250), on_close=lambda *_: self.__modal_done(on_close), open=open)

    def __modal_done(self, on_close):
        assert self.modal
        if on_close:
            on_close(self.modal)
        self.modal = None
        if self.current_animation:
            self.update()
        else:
            # self.controller.next()
            Clock.schedule_once(lambda *_: self.controller.next(), 0.5)

    def piece_size(self):
        return self.cell_size() - 6

    def grid_size(self):
        return min(i-2*j for i, j in zip(self.size, self.margin))

    def set_animation(self, trace):
        assert trace
        if self.current_animation:
            Logger.warn('reversi: set_animation called while another animation pending')
            self.last_move = None # default to controller

        # the horizontal size of the piece, for animated flipping effect
        size = self.piece_size()
        for t in trace:
            row, col, previousOwner = t
            self.current_animation[(row, col)] = (previousOwner, self.controller.owner(row, col), size)
            if Controller.is_nobody(previousOwner):
                self.last_move = (row, col)

    def on_cannot_move(self, _, who):
        if not self.controller.state['game_over']:
            self.message_box(self.theme.cannot_move_title, '{} could not move, lost one turn'.format(who))

    def on_update(self, instance=None, trace=None):
        if trace and not isinstance(instance, Widget):
            self.set_animation(trace)
        elif self.once and (self.size[1] > self.size[0]):
            self.once -= 1
            # adjust margins
            grid_size = self.grid_size()
            self.margin = [ (i - grid_size) / 2 for i in self.size ]
            self.canvas.before.clear()
            with self.canvas.before:
                self.__draw_background()
                self.__draw_grid()
            if self.once:
                self.once -= 1
                MessageBox('Welcome', VERSION.format(self.theme.title))

        had_animation = len(self.current_animation) != 0
        self.canvas.clear()
        with self.canvas:
            bitmaps = [int_to_bits(b, self.dim) for b in self.controller.board_state[:2]]
            for i, b in enumerate(bitmaps):
                self.__draw_bitmap(i ^ 1, b)
        
        self.__finish_update(had_animation)

    def __finish_update(self, had_animation):
        if self.current_animation:
            if not self.modal or not self.modal.open:
                # keep triggering updates until animation completes
                self.update()
        elif had_animation:
            # animation is now complete. is there a pending message box?
            if self.modal and not self.modal.open:
                self.modal.popup.open()
            else:
                self.controller.next()

    def __draw_background(self):
        Color(*self.theme.background_color)
        Rectangle(pos=(0,0), size=self.size)
        Rectangle(pos=(0,0), size=self.size, source=self.theme.background)


    def __draw_bitmap(self, player, bitmap):
        for row in range(self.dim):
            for col in range(self.dim):
                if bitmap[row * self.dim + col]:
                    self.__draw_piece(player, col, self.dim - row - 1)

    def __draw_grid(self):
        cell_size = self.cell_size()
        grid_size = self.grid_size()
        Color(*self.theme.grid_color)

        m = self.margin
        for i in range(0, self.dim+1):
            Line(points=[m[0] + i * cell_size, m[1], m[0] + i * cell_size, m[1] + grid_size], width=1.1)
            Line(points=[m[0], m[1] + i * cell_size, m[0] + grid_size, m[1] + i * cell_size], width=1.1)

    def __draw_texture(self, index, row, col, csize, size):
        x, y = [ m + i * csize + (csize - j)//2 for m, i, j in zip(self.margin, [row, col], size) ]
        Ellipse(pos=(x, y), size=size, texture=self.theme.texture[index])

    def piece_color(self, owner):
        if not self.controller.is_nobody(owner):
            return self.theme.piece_color[owner]

    def __draw_piece(self, player, row, col):
        coords = self.engine_coords(row, col)
        piece_size = self.piece_size()

        (x_size, owner) = self.animated_piece_size(coords, player, piece_size)

        if coords == self.last_move_coords(): # highlight last move
            Color(*self.theme.highlight)
            size = 2 * [piece_size + 6]
            self.__draw_texture(2, row, col, self.cell_size(), size)

        Color(*self.piece_color(owner))
        self.__draw_texture(owner, row, col, self.cell_size(), [ x_size, piece_size ])

    def last_move_coords(self):
        return self.last_move or self.controller.last_move_coords

    @staticmethod
    def step(piece_size):
        return piece_size / max(1, min(10, Clock.get_rfps()))
        
        
    # check pending animation and return horizontal size
    def animated_piece_size(self, coords, owner, piece_size):
        size = piece_size
        a = self.current_animation.get(coords, None)
        if a:
            step = self.step(piece_size)
            prev, current, size = a
            if Controller.is_nobody(prev):
                del self.current_animation[coords]
            elif prev != current:
                owner = prev
                if size > 0:
                    size -= step
                    self.current_animation[coords] = (prev, current, size)
                else:
                    self.current_animation[coords] = (current, current, 0)
            elif size < piece_size:
                size += step
                self.current_animation[coords] = (current, current, size)
            else:
                del self.current_animation[coords]
                size = piece_size
        return (size, owner)

    # convert to engine coords, which start from top left and are in [1, self.dim]
    def engine_coords(self, x, y):
        return x + 1, self.dim - y

    def in_bounds(self, touch):
        return all(0 < i-j < self.grid_size() for i, j in zip(touch.pos, self.margin))

    def on_touch_down(self, touch):
        self.controller.touch()
        cell_size = self.cell_size()
        if self.in_bounds(touch):
            x, y = [ int((i-j) / cell_size) for i, j in zip(touch.pos, self.margin) ]
            self.controller.move(*self.engine_coords(x, y))


class ReversiApp(App):
    icon = ThemeManager.icon()
    __events__ = ( 'on_cannot_move', 'on_game_over', 'on_ready', 'on_update', )

    def __init__(self, dim=8):
        super().__init__()
        log_callback = Logger.trace if is_mobile() else Logger.info
        self.__controller = Controller(dim, self.__dispatch, Clock.schedule_once, log_callback)

        self.btns = {
            'new': Button(text='New', on_press=self.new_game, disabled=True),
            'undo': Button(text='Undo', on_press=self.undo, disabled=True),
            'replay': Button(text='Replay', on_press=self.replay, disabled=True),
            'switch': Button(text='Switch', on_press=self.switch),
        }
        self.info = Label(text='Ready', size_hint=(1, .05), font_size=20)        
        self.board = BoardWidget(self.__controller, log_callback)
        self.bind(on_cannot_move=self.board.on_cannot_move)
        self.bind(on_update=self.board.on_update)
        self.update_events = Clock.schedule_interval(self.__controller.dispatch_messages, 0)
        self.store = DictStore('reversi.data')
        self.load_game()
        self.title = self.board.theme.title

    def build(self):
        self.icon = ThemeManager.icon()
        Window.bind(on_request_close=self.on_quit)
        Window.bind(on_keyboard=self.key_handler)
        if is_mobile():
            Window.maximize()
        else:
            Window.size = (600, 720)
        layout = GridLayout(cols=1)        
        hbox = BoxLayout(orientation='horizontal', size_hint=(1, .1))
        layout.add_widget(hbox)         
        layout.add_widget(self.info)
        vbox = BoxLayout(orientation='horizontal', pos_hint={'center_x': 0.5, 'top': 0.0})
        layout.add_widget(vbox)
        for _, btn in self.btns.items():
            btn.font_size = 20
            hbox.add_widget(btn)
        vbox.add_widget(self.board)
        self.dropdown = DropDown()
        hbox.add_widget(Button(text='Theme', on_release=self.dropdown.open, font_size=20))
        self.build_theme_selection()
        return layout

    def build_theme_selection(self):
        for (theme, dirs, _) in walk(DATA_DIR):
            name = path.split(theme)
            if name[0]:
                btn = ToggleButton(text=name[1], width=80, height=65, size_hint_y=None, group='theme')
                btn.bind(on_release=self.dropdown.select)
                self.dropdown.add_widget(btn)
                if name[1]==self.board.theme.name:
                    btn.state = 'down'

        self.dropdown.bind(on_select=self.select_theme)

    def select_theme(self, _, btn):
        if btn.text == self.board.theme.name:
            btn.state = 'down'
        else:
            self.board.theme = ThemeManager.load(btn.text)
            self.save_game()
            self.board.once = 1
            self.dispatch('on_update')

    # Ctrl+z or Android back button
    def key_handler(self, window, keycode1, keycode2, text, modifiers):
        # self.board.log('modifers: {} {}'.format(modifiers, type(modifiers)))
        undo = keycode1 in [27, 1001] if is_mobile() else (keycode1==122 and 'ctrl' in modifiers)
        if undo:
            self.undo()
            return True
        elif keycode1==27:
            return True # don't close on Escape

    def confirm(self, text, action):        
        def callback(msgbox):
            if msgbox.value == 'Yes':
                return action()
        if not self.board.current_animation:
            self.board.message_box(title='Confirm', text=text + '?', on_close=callback)

    def on_cannot_move(self, who):
        pass

    def on_game_over(self, *score):
        self.info.text = self.__controller.status_info()
        self.board.message_box('Game Over', Controller.format_score(score))

    def on_quit(self, _, source=None):
        self.save_game()
        self.__controller.quit()

    def on_ready(self, *args):
        self.save_game()
        self.dispatch('on_update', *args)
        if not self.board.current_animation:
            self.__controller.next()

    def on_update(self, *_):
        self.info.text = self.__controller.status_info()
        # update button enabled states
        for name, btn in self.btns.items():
            btn.disabled = not self.__controller.state['can_' + name]

    def new_game(self, *_):
        def start_new_game(*_):
            self.__controller.new_game()
            self.save_game() # reset saved
        if self.__controller.state['can_new']:
            if self.__controller.state['game_over']:
                start_new_game()
            else:
                self.confirm('Abandon current game', start_new_game)

    def replay(self, *_):
        if self.__controller.state['can_replay']:
            self.confirm('Replay moves up to this point', self.__controller.replay)

    def switch(self, *_):
        if self.__controller.state['can_switch']:
            machine_player = self.__controller.machine_player_name()
            message = 'Switch sides (and play as {})'.format(machine_player)
            self.confirm(message, self.__controller.switch)

    def undo(self, *_):
        def undo_last(*_):
            self.__controller.undo()
            self.board.last_move = None

        if self.__controller.state['can_undo']:
            self.confirm('Undo last move', undo_last)
    
    def __dispatch(self, msg, args=()):
        self.board.log('dispatch: {} {}'.format(msg, args))
        self.dispatch('on_' + msg, *args)

    def load_game(self):
        self.board.log('reversi: load')
        if self.store.exists(DATA_DIR):
            data = self.store.get(DATA_DIR)
            self.__controller.game_data = data.get('game', [])
            self.board.theme = ThemeManager.load(data.get('theme'))
            self.__controller.update_state()
            self.on_ready()

    def save_game(self):
        self.board.log('reversi: save')
        self.store.put(DATA_DIR, game = self.__controller.game_data, theme=self.board.theme.name)


def main():
    app = ReversiApp(8)
    app.run()
