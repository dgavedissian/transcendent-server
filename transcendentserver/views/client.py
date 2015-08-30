from flask import Blueprint, request, json, abort
from transcendentserver.models import User, Session, Lobby
from transcendentserver.errors import UserDoesNotExist
from transcendentserver.extensions import db, api
from transcendentserver.controls import matchmaking
from transcendentserver.constants import HTTP, LOBBY
from transcendentserver.lib.npid import NPID

from flask_restful import Resource, reqparse

from functools import wraps

client = Blueprint('client', 'transcendentserver')

def json_status(f):
    """
    Call a function and emit any exception raised back to the application
    as a JSON formatted error message.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            if not result:
                result = json.dumps({'success' : True})
            return result
        except Exception as e:
            # TODO: Replace with proper debug logging
            return json.dumps({'success' : False, 'message' : str(e)})
    return wrapper

def post_only(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method != 'POST':
            abort(405)
        else:
            return f(*args, **kwargs)
    return wrapper

def get_session_or_abort():
    """
    Checks the request for the 'auth' parameter and, if it contains one,
    validates it against the sessions database. If at any point the session is
    not found or is invalid, abort the connection with the unauthorized status
    code.
    """
    session_id = request.values.get('auth')
    if not session_id: 
        abort(HTTP.UNAUTHORIZED)

    session = Session.get_if_active(session_id)
    if not session: 
        abort(HTTP.UNAUTHORIZED)

    return session

"""
TODO: Keep this or deprecate this?

class LoginAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('username', type=str, required=True)
        self.reqparse.add_argument('password', type=str, required=True)

    def post(self):
        args = self.reqparse.parse_args()
        name, password = args['username'], args['password']

        current_user = User.find(name)

        if current_user and current_user.check_password(password):
            Session.delete_user_sessions(current_user.id)
            new_session = Session.create_session(current_user)
            return {'success' : True, 'access_code' : new_session.id}, HTTP.OK

        return {'success' : False, 'access_code' : None}, HTTP.UNAUTHORIZED


api.add_resource(LoginAPI, '/v1/login', endpoint='login')
"""

@client.route('/login', methods=('GET', 'POST'))
@post_only
def login():
    name, password = request.form.get('username'), request.form.get('password')
    current_user = User.find(name)

    if not current_user:
        return json.dumps({'success': False, 'access_code': None})

    if current_user and current_user.check_password(password):
        Session.delete_user_sessions(current_user.id)
        
        new_session = Session.create_session(current_user)
        return json.dumps(
           { 'success': True,
             'access_code' : new_session.id
           })

    return json.dumps({'success' : False,'access_code' : None})

@client.route('/logout/')
@post_only
def logout(session_id):
    session = get_session_or_abort()
    
    if not session:
        return json.dumps({'success' : False})
    db.session.delete(session)
    return json.dumps({'success' : True})

@client.route('/server/find')
@json_status
def server_find():
    session = get_session_or_abort()
    game_mode = request.args.get('game_mode')
    if not game_mode: return abort(400)
    possible_lobbies = matchmaking.find_games(game_mode)
    server_count = possible_lobbies.count()
    server_list = [
        { 'id' : lobby.id.hex(),
          'host-GUID' : lobby.host_guid
        } for lobby in possible_lobbies]
    return json.dumps(
        { 'server-count' : server_count,
          'server-list' : server_list,
          'success' : True
        })

@client.route('/server/host', methods=('GET', 'POST'))
@post_only
def host_game():
    session = get_session_or_abort()
    host_guid, game_mode = (request.form.get('guid'), 
                            request.form.get('game_mode'))
    max_players = request.form.get('max_players', LOBBY.MAX_PLAYERS_DEFAULT)

    if not (host_guid and game_mode):
        return abort(400)

    new_lobby = Lobby.create_lobby(host_guid, game_mode, session.user_id, max_players)
    return json.dumps({'success' : True, 'id' : new_lobby.id.hex()})

@client.route('/server/renew', methods=('GET', 'POST'))
@json_status
@post_only
def renew_game():
    session = get_session_or_abort()
    lobby_id = request.form.get('id')

    if not lobby_id:
        return abort(400)

    game = Lobby.get(lobby_id)

    if not game: 
        return json.dumps({'success' : False})

    if session.user.hosts_lobby(game):
        game.renew()
        return json.dumps({'success' : True})

    return json.dumps({'success' : False})

@client.route('/server/remove', methods=('GET', 'POST'))
@json_status
@post_only
def delete_game():
    if request.method != 'POST': abort(405)
    session = get_session_or_abort()
    lobby_id = request.values.get('id')

    if not lobby_id:
        abort(400)

    lobby = Lobby.get(lobby_id)
    if not lobby: return json.dumps({'success' : False})

    if session.user.hosts_lobby(lobby):
        lobby.delete()
        return json.dumps({'success' : True})
    return json.dumps({'success' : False})

@client.route('/server/migrate', methods=('GET', 'POST'))
@json_status
def migrate():
    print
    print 'MIGRATION'
    print
    print request.form.get('auth')
    # I am dubious about this specification. There is a case where if someone
    # hacked the cert of the client, one could migrate all servers as a kind
    # of DoS attack.
    session = get_session_or_abort()

    print session

    lobby_id, new_host_guid = (request.values.get('id'),
                                 request.values.get('guid'))
    print lobby_id, new_host_guid
    lobby = Lobby.get(NPID(hex=lobby_id))
    print lobby
    if not lobby: return json.dumps({'success' : False,
                                     'message': 'Lobby not found'})
    lobby.change_host(session.user, new_host_guid)
    return json.dumps({'success' : True})
    

@client.route('/account/ship/add')
@json_status
def ship_add():
    return None #session_id
