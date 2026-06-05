"""
Seed the database with initial demo data from BRIEFING.md.
Run once: python seed.py
"""
from app import create_app, db
from models import User, Category, Course, Module, Quiz


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        if User.query.first():
            print("Database already seeded — skipping.")
            return

        # ── Users ──────────────────────────────────────────────
        users = [
            User(name='Administrador', email='admin@ibc.com', role='admin'),
            User(name='Prof. Maria', email='tutor@ibc.com', role='tutor'),
            User(name='João Silva', email='joao@ibc.com', role='aluno_interno'),
            User(name='Pedro Costa', email='pedro@email.com', role='aluno_externo'),
        ]
        passwords = ['admin123', 'ibc2024', 'ibc2024', 'ibc2024']
        for u, pw in zip(users, passwords):
            u.set_password(pw)
            db.session.add(u)
        db.session.flush()

        # ── Categories ─────────────────────────────────────────
        cats = {}
        for name in ('Teologia', 'Crescimento', 'Bíblia'):
            c = Category(name=name)
            db.session.add(c)
            db.session.flush()
            cats[name] = c

        # ── Courses ────────────────────────────────────────────
        tutor = users[1]

        courses_data = [
            {
                'name': 'Fundamentos da Fé',
                'icon': '✝️',
                'acesso': 'interno',
                'resumo': 'Um estudo introdutório sobre os pilares da fé cristã...',
                'duracao': '4 semanas',
                'category': 'Teologia',
                'modules': [
                    ('O que é fé?', '30 min'),
                    ('A Bíblia como fundamento', '45 min'),
                    ('Deus Trino', '40 min'),
                    ('Salvação e Graça', '35 min'),
                ],
                'quiz': [
                    ('O que define a fé cristã?', ['Obras', 'Confiança em Deus', 'Tradição', 'Sentimento'], 1, 'Hebreus 11:1'),
                    ('Quantas pessoas há na Trindade?', ['1', '2', '3', '4'], 2, 'Pai, Filho e Espírito Santo'),
                    ('O que é graça?', ['Mérito humano', 'Favor imerecido de Deus', 'Lei mosaica', 'Penitência'], 1, 'Efésios 2:8'),
                    ('Qual livro contém o Salmo 23?', ['Provérbios', 'Jó', 'Salmos', 'Isaías'], 2, 'Salmo 23 está no livro de Salmos'),
                ],
            },
            {
                'name': 'Discipulado Cristão',
                'icon': '🙏',
                'acesso': 'interno',
                'resumo': 'Como crescer na fé e discipular outros...',
                'duracao': '4 semanas',
                'category': 'Crescimento',
                'modules': [
                    ('O chamado ao discipulado', '30 min'),
                    ('Vida de oração', '40 min'),
                    ('Leitura bíblica diária', '35 min'),
                    ('Comunidade cristã', '30 min'),
                ],
                'quiz': [
                    ('Qual é a Grande Comissão?', ['Amar ao próximo', 'Ir e fazer discípulos', 'Guardar o sábado', 'Jejuar'], 1, 'Mateus 28:19-20'),
                    ('O que caracteriza um discípulo?', ['Conhecimento teológico', 'Imitar Jesus', 'Frequentar cultos', 'Pagar dízimos'], 1, 'João 13:35'),
                    ('Com que frequência devemos orar?', ['Apenas domingos', 'Uma vez por dia', 'Incessantemente', 'Quando necessário'], 2, '1 Tessalonicenses 5:17'),
                ],
            },
            {
                'name': 'Estudo Bíblico — Salmos',
                'icon': '📖',
                'acesso': 'publico',
                'resumo': 'Uma jornada pelos salmos mais amados da Bíblia...',
                'duracao': '4 semanas',
                'category': 'Bíblia',
                'modules': [
                    ('Introdução ao livro de Salmos', '25 min'),
                    ('Salmos de louvor', '40 min'),
                    ('Salmos de lamento', '35 min'),
                    ('Salmos messiânicos', '45 min'),
                ],
                'quiz': [
                    ('Quantos salmos há na Bíblia?', ['100', '120', '150', '175'], 2, 'O livro de Salmos tem 150 salmos'),
                    ('Quem escreveu a maioria dos salmos?', ['Moisés', 'Salomão', 'Davi', 'Asafe'], 2, 'Davi escreveu cerca de 73 salmos'),
                    ('"O Senhor é meu pastor" — qual salmo é este?', ['Salmo 1', 'Salmo 23', 'Salmo 91', 'Salmo 119'], 1, 'Salmo 23'),
                ],
            },
        ]

        for cd in courses_data:
            cat = cats[cd['category']]
            course = Course(
                name=cd['name'],
                icon=cd['icon'],
                acesso=cd['acesso'],
                resumo=cd['resumo'],
                duracao=cd['duracao'],
                category_id=cat.id,
                tutor_id=tutor.id,
            )
            db.session.add(course)
            db.session.flush()

            for i, (nome, dur) in enumerate(cd['modules']):
                db.session.add(Module(course_id=course.id, nome=nome, dur=dur, position=i))

            for i, (q, opts, ans, exp) in enumerate(cd['quiz']):
                db.session.add(Quiz(course_id=course.id, q=q, opts=opts, ans=ans, exp=exp, position=i))

        db.session.commit()
        print("Seed concluído com sucesso!")
        print("Usuários criados:")
        for u, pw in zip(users, passwords):
            print(f"  {u.email} / {pw}  [{u.role}]")


if __name__ == '__main__':
    seed()
