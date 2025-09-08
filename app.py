import json
import random
import os
from flask import Flask, request, jsonify

# Flask app initialization
app = Flask(__name__)

# Classes for Blackjack game logic
class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit

    def value(self):
        if self.rank.isdigit():
            return int(self.rank)
        elif self.rank in ['jack', 'queen', 'king']:
            return 10
        elif self.rank == 'ace':
            return 11

    def to_dict(self):
        return {'rank': self.rank, 'suit': self.suit}

class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for suit in ['hearts', 'diamonds', 'clubs', 'spades']
                      for rank in ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'jack', 'queen', 'king', 'ace']]
        random.shuffle(self.cards)

class Player:
    def __init__(self, name, balance=20000):
        self.name = name
        self.hand = []
        self.stopped = False
        self.is_dealer = name == "Dealer"
        self.balance = balance
        self.bet = 0
        self.history = []

    def hit(self, card):
        self.hand.append(card)

    def calculate_score(self):
        score, aces = 0, 0
        for card in self.hand:
            value = card.value()
            if card.rank == 'ace':
                aces += 1
            score += value
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score

    def to_dict(self, hide_dealer_card=False):
        hand_to_send = [card.to_dict() for card in self.hand]
        if self.is_dealer and hide_dealer_card and len(hand_to_send) > 1:
            hand_to_send[1] = {'rank': 'back', 'suit': 'back'} # Placeholder for the face-down card
        
        return {
            'name': self.name,
            'hand': hand_to_send,
            'score': self.calculate_score(),
            'balance': self.balance,
            'bet': self.bet,
            'stopped': self.stopped,
            'history': self.history
        }

# Global game state (This would be replaced by a database in a real-world app)
game_state = {
    'deck': Deck(),
    'players': [],
    'dealer': Player("Dealer"),
    'current_player_index': 0,
    'game_over': False
}

def reset_game():
    global game_state
    
    # Store players' balances and history before resetting
    player_data = {p.name: {'balance': p.balance, 'history': p.history} for p in game_state['players']}
    
    game_state['deck'] = Deck()
    game_state['players'] = [Player(name, balance=data['balance']) for name, data in player_data.items()]
    game_state['dealer'] = Player("Dealer")
    game_state['current_player_index'] = 0
    game_state['game_over'] = False

@app.route('/api/start_game', methods=['POST'])
def start_game():
    data = request.json
    player_names = data.get('players', [])
    
    # If starting a new game, reset everything.
    global game_state
    game_state['players'] = [Player(name) for name in player_names]
    game_state['dealer'] = Player("Dealer")
    game_state['current_player_index'] = 0
    game_state['game_over'] = False
    
    # Deal initial cards
    for _ in range(2):
        for player in game_state['players']:
            player.hit(game_state['deck'].cards.pop())
        game_state['dealer'].hit(game_state['deck'].cards.pop())
        
    response = {
        'players': [p.to_dict() for p in game_state['players']],
        'dealer': game_state['dealer'].to_dict(hide_dealer_card=True),
        'current_player': game_state['players'][game_state['current_player_index']].name,
        'game_over': False
    }
    return jsonify(response)

@app.route('/api/place_bet', methods=['POST'])
def place_bet():
    data = request.json
    player_name = data.get('player')
    bet_amount = data.get('bet')
    
    player = next((p for p in game_state['players'] if p.name == player_name), None)
    
    if player and bet_amount <= player.balance:
        player.bet = bet_amount
        response = {
            'players': [p.to_dict() for p in game_state['players']],
            'dealer': game_state['dealer'].to_dict(hide_dealer_card=True),
            'current_player': game_state['players'][game_state['current_player_index']].name,
            'message': f"Bet of {bet_amount} placed for {player_name}."
        }
        return jsonify(response)
    else:
        return jsonify({"error": "Invalid player or bet amount."}), 400

@app.route('/api/hit', methods=['POST'])
def hit():
    global game_state
    current_player_idx = game_state['current_player_index']
    player = game_state['players'][current_player_idx]
    
    new_card = game_state['deck'].cards.pop()
    player.hit(new_card)

    if player.calculate_score() >= 21:
        player.stopped = True
        game_state['current_player_index'] += 1
    
    return jsonify(get_game_state())

@app.route('/api/stop', methods=['POST'])
def stop():
    global game_state
    current_player_idx = game_state['current_player_index']
    player = game_state['players'][current_player_idx]
    player.stopped = True
    game_state['current_player_index'] += 1
    
    return jsonify(get_game_state())

@app.route('/api/dealer_turn', methods=['POST'])
def dealer_turn():
    global game_state
    
    # Dealer's turn logic
    while game_state['dealer'].calculate_score() < 17:
        new_card = game_state['deck'].cards.pop()
        game_state['dealer'].hit(new_card)
        
    game_state['game_over'] = True
    
    # Calculate results
    dealer_score = game_state['dealer'].calculate_score()
    for player in game_state['players']:
        player_score = player.calculate_score()
        result_text = ""
        if player_score > 21:
            player.balance -= player.bet
            result_text = f"Bust! Lost {player.bet}"
        elif dealer_score > 21 or player_score > dealer_score:
            win_amount = player.bet * 2
            player.balance += win_amount
            result_text = f"Won {player.bet}"
        elif player_score == dealer_score:
            result_text = "Push"
        else:
            player.balance -= player.bet
            result_text = f"Lost {player.bet}"
        
        player.history.append({"bet": player.bet, "result": result_text, "balance": player.balance})
        
    return jsonify(get_game_state())

@app.route('/api/reset', methods=['POST'])
def reset():
    reset_game()
    return jsonify({"message": "Game reset."})

def get_game_state():
    all_players_stopped = all(p.stopped or p.calculate_score() >= 21 for p in game_state['players'])
    
    if all_players_stopped and not game_state['game_over']:
        return {
            'players': [p.to_dict() for p in game_state['players']],
            'dealer': game_state['dealer'].to_dict(), # Show dealer's hand
            'current_player': 'Dealer',
            'game_over': True
        }
    
    return {
        'players': [p.to_dict() for p in game_state['players']],
        'dealer': game_state['dealer'].to_dict(hide_dealer_card=not all_players_stopped),
        'current_player': game_state['players'][game_state['current_player_index']].name if game_state['current_player_index'] < len(game_state['players']) else 'Dealer',
        'game_over': game_state['game_over']
    }

@app.route('/api/state')
def get_state():
    return jsonify(get_game_state())

# The following is needed for Vercel deployment
from flask import send_from_directory

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    app.run(debug=True)
