# Простое in-memory хранилище состояния пользователей

user_state = {}

def set_user_state(user_id, state):
    user_state[user_id] = state

def get_user_state(user_id):
    return user_state.get(user_id)

def clear_user_state(user_id):
    user_state.pop(user_id, None)
