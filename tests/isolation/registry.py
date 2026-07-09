"""
Registro de cobertura de isolamento (doc 02 §5.4 / NFR-01).

TODO endpoint da aplicação DEVE estar classificado aqui. O teste de cobertura
(test_endpoint_coverage.py) FALHA o pipeline se:
  - um endpoint novo aparecer sem classificação (regra central da suíte), ou
  - uma entrada do registro apontar para endpoint que não existe mais (lixo).

Classificações:
  TENANT_SCOPED   endpoint que lê/escreve dado com tenant_id — precisa de
                  caso de isolamento em tests/isolation/ (nome do teste na
                  entrada). Hoje: só a superfície de tenancy da Fase 2.
  LEGACY_PRE_TENANCY  endpoint sobre tabela legada SEM tenant_id ainda.
                  Vai migrando para TENANT_SCOPED grupo a grupo na Fase 3
                  (gamificação → progresso → conteúdo). Um endpoint só pode
                  ficar aqui enquanto a tabela não tiver tenant_id.
  PUBLIC_INFRA    infra sem dado de domínio (health, estáticos, SPA).
"""

# ── Superfície tenant-scoped (Fase 2) ────────────────────────────────────
# endpoint → teste que prova o isolamento
TENANT_SCOPED = {
    'tenant_current': 'test_tenant_isolation.py::test_tenant_current_nao_vaza_outro_tenant',
    # grupo 1 — gamificação (Fase 3)
    'gamification.user_stats': 'test_gamification_isolation.py::test_pontos_independentes_por_tenant',
    'gamification.list_badges': 'test_gamification_isolation.py::test_badges_desbloqueados_nao_vazam',
    'gamification.check_badge_progress': 'test_gamification_isolation.py::test_badges_desbloqueados_nao_vazam',
    'gamification.add_points': 'test_gamification_isolation.py::test_pontos_independentes_por_tenant',
    'certificates.my_certificates': 'test_gamification_isolation.py::test_certificados_nao_vazam_entre_tenants',
    'certificates.issue_certificate': 'test_gamification_isolation.py::test_certificados_nao_vazam_entre_tenants',
    'dashboards.activity_feed': 'test_gamification_isolation.py::test_mural_de_atividades_por_tenant',
    'aluno.achievements': 'test_gamification_isolation.py::test_pontos_independentes_por_tenant',
    'aluno.certificates': 'test_gamification_isolation.py::test_certificados_nao_vazam_entre_tenants',
    # verify/download por cert_code são lookups globais INTENCIONAIS
    # (verificação pública por código único não-adivinhável) — ver
    # routes/certificates.py; classificados aqui com caso do grupo.
    'certificates.verify_certificate': 'test_gamification_isolation.py::test_certificados_nao_vazam_entre_tenants',
    'certificates.download_certificate': 'test_gamification_isolation.py::test_certificados_nao_vazam_entre_tenants',
}

# ── Infra pública (sem dado de domínio) ──────────────────────────────────
PUBLIC_INFRA = {
    'health',
    'home',
    'frontend',
    'favicon',
    'serve_css',
    'serve_icon_sprite',
    'serve_images',
    'serve_upload',        # dado de curso, mas o controle é por material (Fase 3)
}

# ── Legado pré-tenancy (Fase 3 migra grupo a grupo) ──────────────────────
LEGACY_PRE_TENANCY = {
    # admin
    'admin.admin_reset_user_password',
    'admin.assign_course_to_tutor',
    'admin.assign_question',
    'admin.bulk_action_users',
    'admin.change_user_active_trail',
    'admin.create_announcement',
    'admin.delete_announcement',
    'admin.duplicate_course',
    'admin.get_admin_config',
    'admin.get_user_profile',
    'admin.invite_user',
    'admin.list_announcements',
    'admin.list_courses_simple',
    'admin.list_levels',
    'admin.list_tutors',
    'admin.list_unassigned_questions',
    'admin.list_users',
    'admin.replace_levels',
    'admin.reset_user_progress',
    'admin.send_user_message',
    'admin.toggle_course_status',
    'admin.toggle_user_active',
    'admin.unassign_course_from_tutor',
    'admin.update_admin_config',
    'admin.update_user',
    # aluno
    'aluno.continue_learning',
    'aluno.my_questions_with_status',
    'aluno.resolve_question',
    'aluno.save_study_time',
    'aluno.stats',
    # (raiz)
    'api_user',
    # auth
    'auth.change_password',
    'auth.delete_user',
    'auth.forgot_password',
    'auth.get_user',
    'auth.list_users',
    'auth.login',
    'auth.logout',
    'auth.register',
    'auth.reset_password',
    'auth.reset_password_token',
    'auth.signup',
    'auth.update_profile',
    # certificates
    # courses
    'courses.add_material',
    'courses.add_module',
    'courses.admin_add_material',
    'courses.admin_delete_lesson',
    'courses.admin_delete_material',
    'courses.admin_get_lessons',
    'courses.admin_list_courses',
    'courses.admin_reorder_lessons',
    'courses.admin_update_exercise',
    'courses.admin_update_lesson',
    'courses.create_course',
    'courses.delete_course',
    'courses.delete_material',
    'courses.delete_module',
    'courses.get_course',
    'courses.list_categories',
    'courses.list_courses',
    'courses.update_course',
    # dashboards
    'dashboards.admin_dashboard',
    'dashboards.aluno_dashboard',
    'dashboards.aluno_externo_dashboard',
    'dashboards.tutor_dashboard',
    # gamification
    # lessons
    'lessons.get_aula',
    'lessons.list_aulas',
    'lessons.mark_video_watched',
    'lessons.next_lesson',
    'lessons.submit_aula_quiz',
    'lessons.update_module_video',
    # materials
    'materials.get_material',
    'materials.save_read_progress',
    'materials.serve_material_file',
    'materials.upload_material',
    # notifications
    'notifications.dismiss_announcement',
    'notifications.get_gamification_config',
    'notifications.get_public_config',
    'notifications.list_active_announcements',
    'notifications.list_notifications',
    'notifications.mark_all_notifications_read',
    'notifications.mark_notification_read',
    # onboarding
    'onboarding.onboarding_status',
    'onboarding.submit_onboarding',
    # progress
    'progress.get_progress',
    'progress.quiz_result',
    'progress.save_progress',
    'progress.submit_quiz',
    # questions
    'questions.answer_question',
    'questions.ask_question',
    'questions.list_questions',
    'questions.my_questions',
    'questions.tutor_dashboard',
    # trails
    'trails.active_trail',
    'trails.admin_add_course_to_trail',
    'trails.admin_available_courses_for_trail',
    'trails.admin_list_trails',
    'trails.admin_remove_course_from_trail',
    'trails.admin_reorder_trail_courses',
    'trails.admin_update_trail',
    'trails.create_trail',
    'trails.enroll_trail',
    'trails.focus_trail',
    'trails.list_trails',
    'trails.my_trails',
    # (raiz)
    'upload_file',
}
