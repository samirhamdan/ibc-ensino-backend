import sys
import os
from app import create_app, db
from app.models import Usuario

if len(sys.argv) < 2:
    print("❌ Use: python make_admin.py seu-email@ibc.com")
    sys.exit(1)

email = sys.argv[1]

app = create_app('production')
with app.app_context():
    user = Usuario.query.filter_by(email=email).first()
    if user:
        user.perfil = 'admin'
        db.session.commit()
        print(f'✅ {user.email} agora é admin!')
    else:
        print(f'❌ Usuário {email} não encontrado')
