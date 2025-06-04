# tokens.py
PLAN_TOKEN_AMOUNTS = {'free': 50, 'pro': 1000, 'pro+': 2500}
TOKEN_COSTS = {'image': 1, 'video': 2}

def get_plan_tokens(plan):
    return PLAN_TOKEN_AMOUNTS.get(plan, 0)

def deduct_tokens(user, amount, db):
    if user.tokens >= amount:
        user.tokens -= amount
        db.session.commit()
        return True
    return False

def reset_user_tokens(user, db):
    user.tokens = get_plan_tokens(user.plan)
    db.session.commit()
