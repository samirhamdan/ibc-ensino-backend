"""
Seed the database with initial demo data from BRIEFING.md.
Run once: python seed.py
"""
from app import create_app, db
from models import User, Category, Course, Module, Quiz, Material, Badge, Trail, TrailCourse, Certificate, PlatformConfig, Level, Achievement

LEVELS = [
    (1, 'Iniciante', 0, '#95a5a6'),
    (2, 'Aprendiz', 100, '#3498db'),
    (3, 'Dedicado', 300, '#27ae60'),
    (4, 'Comprometido', 600, '#f39c12'),
    (5, 'Mestre', 1000, '#e74c3c'),
    (6, 'Discípulo', 2000, '#9b59b6'),
    (7, 'Líder', 5000, '#e67e22'),
]


def seed_config():
    if PlatformConfig.query.first():
        return
    db.session.add(PlatformConfig(
        platform_name='IBC Ensino',
        platform_short='IBC',
        whatsapp='(67) 99999-9999',
        support_email='contato@ibccg.org.br',
        support_hours='Seg-Sex, 8h-17h',
        verse_text='Lâmpada para os meus pés é a tua palavra e luz para o meu caminho.',
        verse_reference='Salmos 119:105',
        points_read_material=10,
        points_complete_video=10,
        points_correct_exercise=20,
        points_complete_course=50,
        points_complete_trail=200,
    ))
    db.session.commit()
    print("Configuração da plataforma criada.")


def seed_levels():
    for number, name, min_points, color in LEVELS:
        if Level.query.filter_by(number=number).first():
            continue
        db.session.add(Level(number=number, name=name, min_points=min_points, color=color))
    db.session.commit()
    print("Níveis verificados/criados.")

BADGES = [
    ('novo_discipulo', 'Novo Discípulo', 'Seu primeiro curso começado', '👶', 'comum'),
    ('estudioso_palavra', 'Estudioso da Palavra', 'Leu 5 materiais completos (≥50%)', '📖', 'comum'),
    ('guerreiro_palavra', 'Guerreiro da Palavra', 'Passou em 3 quizzes de primeira', '⚔️', 'raro'),
    ('buscador_verdade', 'Buscador de Verdade', 'Fez 5+ perguntas no curso', '💡', 'comum'),
    ('iluminado_graca', 'Iluminado pela Graça', 'Sua pergunta recebeu resposta do tutor', '✨', 'raro'),
    ('edificador', 'Edificador', 'Concluiu 3 cursos completos', '👑', 'épico'),
    ('corredor_incansavel', 'Corredor Incansável', 'Concluiu curso em 7 dias', '🔥', 'comum'),
    ('servo_fiel', 'Servo Fiel', 'Estudou 7 dias seguidos', '💪', 'raro'),
    # Trail badges
    ('trilha_evangelismo', 'Evangelizador', 'Concluiu a Trilha de Evangelismo', '📢', 'épico'),
    ('trilha_discipulado', 'Discípulo Fiel', 'Concluiu a Trilha de Discipulado', '🙏', 'épico'),
    ('trilha_teologia', 'Teólogo', 'Concluiu a Trilha de Teologia', '✝️', 'épico'),
    ('trilha_servico', 'Servo do Senhor', 'Concluiu a Trilha de Serviço', '🤝', 'épico'),
]


def seed_badges():
    """Catálogo de badges POR TENANT (GAM-01: gamificação por tenant).
    Requer seed_tenants() antes. Idempotente por (tenant, code)."""
    from core.tenancy import Tenant
    for tenant in Tenant.query.all():
        for code, name, desc, icon, rarity in BADGES:
            if Badge.query.filter_by(code=code, tenant_id=tenant.id).first():
                continue
            db.session.add(Badge(code=code, name=name, description=desc,
                                 icon=icon, rarity=rarity, tenant_id=tenant.id))
    db.session.commit()
    print("Badges verificadas/criadas (por tenant).")


ACHIEVEMENTS = [
    ('primeira_aula', 'Primeira Aula Concluída', 'Concluiu sua primeira aula na plataforma', '🎬', 'lessons_completed', 1, 10),
    ('dez_aulas', '10 Aulas Concluídas', 'Concluiu 10 aulas na plataforma', '📚', 'lessons_completed', 10, 30),
    ('vinte_cinco_aulas', '25 Aulas Concluídas', 'Concluiu 25 aulas na plataforma', '📘', 'lessons_completed', 25, 60),
    ('primeiro_curso', 'Primeiro Curso Concluído', 'Concluiu seu primeiro curso completo', '🎓', 'courses_completed', 1, 50),
    ('cinco_cursos', '5 Cursos Concluídos', 'Concluiu 5 cursos completos', '🏅', 'courses_completed', 5, 150),
    ('dez_cursos', '10 Cursos Concluídos', 'Concluiu 10 cursos completos', '🏆', 'courses_completed', 10, 300),
    ('primeira_trilha', 'Primeira Trilha Concluída', 'Concluiu sua primeira trilha de aprendizado', '🛤️', 'trails_completed', 1, 100),
    ('duas_trilhas', '2 Trilhas Concluídas', 'Concluiu 2 trilhas de aprendizado', '🗺️', 'trails_completed', 2, 200),
    ('primeira_pergunta', 'Primeira Pergunta', 'Fez sua primeira pergunta a um tutor', '💬', 'questions_created', 1, 10),
    ('cinco_perguntas', '5 Perguntas Feitas', 'Fez 5 perguntas a tutores', '🙋', 'questions_created', 5, 25),
    ('primeiro_certificado', 'Primeiro Certificado', 'Conquistou seu primeiro certificado', '📜', 'certificates_earned', 1, 50),
    ('cinco_certificados', '5 Certificados', 'Conquistou 5 certificados', '🎖️', 'certificates_earned', 5, 150),
]


def seed_achievements():
    """Catálogo de conquistas POR TENANT. Requer seed_tenants() antes."""
    from core.tenancy import Tenant
    for tenant in Tenant.query.all():
        for code, name, desc, icon, criteria_type, criteria_value, points_reward in ACHIEVEMENTS:
            if Achievement.query.filter_by(code=code, tenant_id=tenant.id).first():
                continue
            db.session.add(Achievement(
                code=code, name=name, description=desc, icon=icon,
                criteria_type=criteria_type, criteria_value=criteria_value,
                points_reward=points_reward, tenant_id=tenant.id,
            ))
    db.session.commit()
    print("Conquistas (achievements) verificadas/criadas (por tenant).")


def seed_tenants():
    """TEN-01 (Fase 2): tenants de desenvolvimento ibc e demo. Idempotente."""
    from core.tenancy import Tenant
    for slug, nome, sub in (('ibc', 'IBC Ensino', 'ibc'), ('demo', 'Tenant Demo', 'demo')):
        if not Tenant.query.filter_by(slug=slug).first():
            db.session.add(Tenant(slug=slug, nome=nome, subdominio=sub,
                                  tema_json={'cor_primaria': '#008ea8'}))
    db.session.commit()
    print("Tenants de desenvolvimento verificados/criados (ibc, demo).")


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()
        seed_tenants()   # PRIMEIRO: badges/achievements são por tenant
        seed_badges()
        seed_config()
        seed_levels()
        seed_achievements()

        if User.query.first():
            print("Database already seeded — skipping.")
            return

        # ── Users ──────────────────────────────────────────────
        users = [
            User(name='Administrador', email='admin@ibc.com', role='admin'),
            User(name='Prof. Maria', email='tutor@ibc.com', role='tutor'),
            User(name='João Silva', email='joao@ibc.com', role='aluno'),
            User(name='Pedro Costa', email='pedro@email.com', role='aluno'),
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
                'aulas': [
                    {'nome': 'O que é fé?', 'dur': '30 min',
                     'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                     'material': ('Apostila — O que é fé?', 'https://example.com/fe.pdf', 'link'),
                     'quiz': [('O que define a fé cristã?', ['Obras', 'Confiança em Deus', 'Tradição', 'Sentimento'], 1, 'Hebreus 11:1')]},
                    {'nome': 'A Bíblia como fundamento', 'dur': '45 min',
                     'material': ('Apostila — A Bíblia', 'https://example.com/biblia.pdf', 'link'),
                     'quiz': [('Qual livro contém o Salmo 23?', ['Provérbios', 'Jó', 'Salmos', 'Isaías'], 2, 'Salmo 23 está no livro de Salmos')]},
                    {'nome': 'Deus Trino', 'dur': '40 min',
                     'material': ('Apostila — Deus Trino', 'https://example.com/trindade.pdf', 'link'),
                     'quiz': [('Quantas pessoas há na Trindade?', ['1', '2', '3', '4'], 2, 'Pai, Filho e Espírito Santo')]},
                    {'nome': 'Salvação e Graça', 'dur': '35 min',
                     'material': ('Apostila — Salvação', 'https://example.com/salvacao.pdf', 'link'),
                     'quiz': [('O que é graça?', ['Mérito humano', 'Favor imerecido de Deus', 'Lei mosaica', 'Penitência'], 1, 'Efésios 2:8')]},
                ],
            },
            {
                'name': 'Discipulado Cristão',
                'icon': '🙏',
                'acesso': 'interno',
                'resumo': 'Como crescer na fé e discipular outros...',
                'duracao': '4 semanas',
                'category': 'Crescimento',
                'aulas': [
                    {'nome': 'O chamado ao discipulado', 'dur': '30 min',
                     'video_url': 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
                     'material': ('Apostila — Discipulado', 'https://example.com/discipulado.pdf', 'link'),
                     'quiz': [('Qual é a Grande Comissão?', ['Amar ao próximo', 'Ir e fazer discípulos', 'Guardar o sábado', 'Jejuar'], 1, 'Mateus 28:19-20')]},
                    {'nome': 'Vida de oração', 'dur': '40 min',
                     'material': ('Apostila — Oração', 'https://example.com/oracao.pdf', 'link'),
                     'quiz': [('Com que frequência devemos orar?', ['Apenas domingos', 'Uma vez por dia', 'Incessantemente', 'Quando necessário'], 2, '1 Tessalonicenses 5:17')]},
                    {'nome': 'Leitura bíblica diária', 'dur': '35 min',
                     'material': ('Apostila — Leitura bíblica', 'https://example.com/leitura.pdf', 'link'),
                     'quiz': [('O que caracteriza um discípulo?', ['Conhecimento teológico', 'Imitar Jesus', 'Frequentar cultos', 'Pagar dízimos'], 1, 'João 13:35')]},
                    {'nome': 'Comunidade cristã', 'dur': '30 min',
                     'material': ('Apostila — Comunidade', 'https://example.com/comunidade.pdf', 'link'),
                     'quiz': [('Por que a comunhão é importante?', ['Tradição', 'Edificação mútua', 'Obrigação', 'Status social'], 1, 'Hebreus 10:24-25')]},
                ],
            },
            {
                'name': 'Estudo Bíblico — Salmos',
                'icon': '📖',
                'acesso': 'publico',
                'resumo': 'Uma jornada pelos salmos mais amados da Bíblia...',
                'duracao': '4 semanas',
                'category': 'Bíblia',
                'aulas': [
                    {'nome': 'Introdução ao livro de Salmos', 'dur': '25 min',
                     'material': ('Apostila — Introdução', 'https://example.com/salmos-intro.pdf', 'link'),
                     'quiz': [('Quantos salmos há na Bíblia?', ['100', '120', '150', '175'], 2, 'O livro de Salmos tem 150 salmos')]},
                    {'nome': 'Salmos de louvor', 'dur': '40 min',
                     'material': ('Apostila — Louvor', 'https://example.com/louvor.pdf', 'link'),
                     'quiz': [('Quem escreveu a maioria dos salmos?', ['Moisés', 'Salomão', 'Davi', 'Asafe'], 2, 'Davi escreveu cerca de 73 salmos')]},
                    {'nome': 'Salmos de lamento', 'dur': '35 min',
                     'material': ('Apostila — Lamento', 'https://example.com/lamento.pdf', 'link'),
                     'quiz': [('"O Senhor é meu pastor" — qual salmo é este?', ['Salmo 1', 'Salmo 23', 'Salmo 91', 'Salmo 119'], 1, 'Salmo 23')]},
                    {'nome': 'Salmos messiânicos', 'dur': '45 min',
                     'material': ('Apostila — Messiânicos', 'https://example.com/messianicos.pdf', 'link'),
                     'quiz': [('Qual salmo é citado como messiânico no Novo Testamento?', ['Salmo 22', 'Salmo 100', 'Salmo 136', 'Salmo 150'], 0, 'Salmo 22 é citado na crucificação de Jesus')]},
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

            for i, aula in enumerate(cd['aulas']):
                from routes.lessons import get_embed_url
                vurl = aula.get('video_url')
                _, vprov = get_embed_url(vurl)
                module = Module(course_id=course.id, nome=aula['nome'], dur=aula['dur'], position=i,
                                video_url=vurl, video_provider=vprov)
                db.session.add(module)
                db.session.flush()

                mat_name, mat_url, mat_tipo = aula['material']
                db.session.add(Material(course_id=course.id, module_id=module.id,
                                        name=mat_name, url=mat_url, tipo=mat_tipo))

                for j, (q, opts, ans, exp) in enumerate(aula['quiz']):
                    db.session.add(Quiz(course_id=course.id, module_id=module.id,
                                        q=q, opts=opts, ans=ans, exp=exp, position=j))

        db.session.commit()

        # ── Trails ─────────────────────────────────────────────
        from core.tenancy import current_tenant_id
        courses_by_name = {c.name: c for c in
                           Course.query.filter_by(tenant_id=current_tenant_id()).all()}
        trails_data = [
            {
                'name': 'Trilha do Evangelismo',
                'description': 'Aprenda a compartilhar o evangelho com clareza e amor.',
                'icon': '📢',
                'goal': 'evangelismo',
                'xp_bonus': 150,
                'badge_code': 'trilha_evangelismo',
                'courses': ['Estudo Bíblico — Salmos', 'Fundamentos da Fé'],
            },
            {
                'name': 'Trilha do Discipulado',
                'description': 'Cresça em fé e aprenda a fazer discípulos.',
                'icon': '🙏',
                'goal': 'discipulado',
                'xp_bonus': 150,
                'badge_code': 'trilha_discipulado',
                'courses': ['Discipulado Cristão', 'Fundamentos da Fé'],
            },
            {
                'name': 'Trilha de Teologia',
                'description': 'Aprofunde seu conhecimento dos fundamentos teológicos.',
                'icon': '✝️',
                'goal': 'teologia',
                'xp_bonus': 200,
                'badge_code': 'trilha_teologia',
                'courses': ['Fundamentos da Fé', 'Estudo Bíblico — Salmos'],
            },
            {
                'name': 'Trilha de Serviço',
                'description': 'Descubra seu chamado e sirva com excelência na Igreja.',
                'icon': '🤝',
                'goal': 'servico',
                'xp_bonus': 150,
                'badge_code': 'trilha_servico',
                'courses': ['Discipulado Cristão', 'Estudo Bíblico — Salmos'],
            },
        ]

        for td in trails_data:
            trail = Trail(
                name=td['name'],
                description=td['description'],
                icon=td['icon'],
                goal=td['goal'],
                xp_bonus=td['xp_bonus'],
                badge_code=td['badge_code'],
            )
            db.session.add(trail)
            db.session.flush()
            for pos, cname in enumerate(td['courses']):
                course = courses_by_name.get(cname)
                if course:
                    db.session.add(TrailCourse(trail_id=trail.id, course_id=course.id, position=pos))

        # admin and tutor skip onboarding
        for u in users:
            if u.role in ('admin', 'tutor'):
                u.onboarding_completed = True

        db.session.commit()
        print("Seed concluído com sucesso!")
        print("Usuários criados:")
        for u, pw in zip(users, passwords):
            print(f"  {u.email} / {pw}  [{u.role}]")


if __name__ == '__main__':
    seed()
