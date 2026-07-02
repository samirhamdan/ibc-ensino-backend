import sys
from app import create_app, db

app = create_app('production')
with app.app_context():
    from models import Usuario
    
    if len(sys.argv) < 2:
        email = input("Email do usuário: ")
    else:
        email = sys.argv[1]
    
    user = Usuario.query.filter_by(email=email).first()
    if user:
        user.perfil = 'admin'
        db.session.commit()
        print(f'✅ {user.email} agora é admin!')
    else:
        print(f'❌ Usuário {email} não encontrado')
