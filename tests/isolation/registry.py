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
    'theme.get_theme': 'test_tenant_isolation.py::test_theme_por_tenant_nao_vaza',
    'theme.get_theme_json': 'test_tenant_isolation.py::test_theme_por_tenant_nao_vaza',
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
    # grupo 2 — progresso (Fase 3)
    'lessons.list_aulas': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'lessons.get_aula': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'lessons.submit_aula_quiz': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'lessons.next_lesson': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'lessons.mark_video_watched': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'materials.save_read_progress': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'progress.get_progress': 'test_progress_isolation.py::test_progresso_legado_zero_linhas_cruzadas',
    'progress.save_progress': 'test_progress_isolation.py::test_progresso_legado_zero_linhas_cruzadas',
    'progress.submit_quiz': 'test_progress_isolation.py::test_progresso_legado_zero_linhas_cruzadas',
    'progress.quiz_result': 'test_progress_isolation.py::test_progresso_legado_zero_linhas_cruzadas',
    'trails.my_trails': 'test_progress_isolation.py::test_matricula_em_trilha_nao_vaza',
    'trails.enroll_trail': 'test_progress_isolation.py::test_matricula_em_trilha_nao_vaza',
    'trails.active_trail': 'test_progress_isolation.py::test_matricula_em_trilha_nao_vaza',
    'trails.focus_trail': 'test_progress_isolation.py::test_matricula_em_trilha_nao_vaza',
    'onboarding.submit_onboarding': 'test_progress_isolation.py::test_onboarding_answer_por_tenant',
    'aluno.save_study_time': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'aluno.stats': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    'aluno.continue_learning': 'test_progress_isolation.py::test_progresso_de_aula_nao_desbloqueia_em_outro_tenant',
    # grupo 3 — conteúdo (Fase 3, fecha TEN-01)
    'courses.list_courses': 'test_content_isolation.py::test_catalogo_por_tenant',
    'courses.get_course': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.create_course': 'test_content_isolation.py::test_catalogo_por_tenant',
    'courses.update_course': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.delete_course': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.add_module': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.delete_module': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.add_material': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.delete_material': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.list_categories': 'test_content_isolation.py::test_catalogo_por_tenant',
    'courses.admin_list_courses': 'test_content_isolation.py::test_catalogo_por_tenant',
    'courses.admin_get_lessons': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.admin_update_lesson': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.admin_delete_lesson': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.admin_reorder_lessons': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.admin_update_exercise': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.admin_add_material': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'courses.admin_delete_material': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'lessons.update_module_video': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'materials.get_material': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'materials.serve_material_file': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'materials.upload_material': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'trails.list_trails': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.admin_list_trails': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.create_trail': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.admin_update_trail': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.admin_add_course_to_trail': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.admin_remove_course_from_trail': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.admin_reorder_trail_courses': 'test_content_isolation.py::test_trilhas_por_tenant',
    'trails.admin_available_courses_for_trail': 'test_content_isolation.py::test_trilhas_por_tenant',
    'questions.list_questions': 'test_content_isolation.py::test_perguntas_por_tenant',
    'questions.ask_question': 'test_content_isolation.py::test_perguntas_por_tenant',
    'questions.answer_question': 'test_content_isolation.py::test_perguntas_por_tenant',
    'questions.my_questions': 'test_content_isolation.py::test_perguntas_por_tenant',
    'questions.tutor_dashboard': 'test_content_isolation.py::test_perguntas_por_tenant',
    'aluno.my_questions_with_status': 'test_content_isolation.py::test_perguntas_por_tenant',
    'aluno.resolve_question': 'test_content_isolation.py::test_perguntas_por_tenant',
    'notifications.list_notifications': 'test_content_isolation.py::test_notificacoes_por_tenant',
    'notifications.mark_notification_read': 'test_content_isolation.py::test_notificacoes_por_tenant',
    'notifications.mark_all_notifications_read': 'test_content_isolation.py::test_notificacoes_por_tenant',
    'notifications.list_active_announcements': 'test_content_isolation.py::test_avisos_ativos_por_tenant',
    'notifications.dismiss_announcement': 'test_content_isolation.py::test_avisos_ativos_por_tenant',
    'admin.create_announcement': 'test_content_isolation.py::test_avisos_ativos_por_tenant',
    'admin.list_announcements': 'test_content_isolation.py::test_avisos_ativos_por_tenant',
    'admin.delete_announcement': 'test_content_isolation.py::test_avisos_ativos_por_tenant',
    'admin.list_courses_simple': 'test_content_isolation.py::test_catalogo_por_tenant',
    'admin.toggle_course_status': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'admin.duplicate_course': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'admin.assign_course_to_tutor': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'admin.unassign_course_from_tutor': 'test_content_isolation.py::test_curso_de_outro_tenant_404_por_id_direto',
    'admin.list_unassigned_questions': 'test_content_isolation.py::test_perguntas_por_tenant',
    'admin.assign_question': 'test_content_isolation.py::test_perguntas_por_tenant',
    'dashboards.aluno_dashboard': 'test_content_isolation.py::test_catalogo_por_tenant',
    'dashboards.aluno_externo_dashboard': 'test_content_isolation.py::test_catalogo_por_tenant',
    'dashboards.tutor_dashboard': 'test_content_isolation.py::test_catalogo_por_tenant',
    'dashboards.admin_dashboard': 'test_content_isolation.py::test_catalogo_por_tenant',
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

# ── Legado com justificativa (não migra na Fase 3) ───────────────────────
LEGACY_PRE_TENANCY = {
    # users é GLOBAL por design (doc 02 §4: papéis por tenant vivem em
    # tenant_users) — endpoints de identidade/gestão de usuário viram
    # tenant-aware na Fase 4 (AUTH-01/AUTH-03, JWT com claims de tenant)
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
    'api_user',
    'admin.list_users',
    'admin.update_user',
    'admin.get_user_profile',
    'admin.admin_reset_user_password',
    'admin.reset_user_progress',
    'admin.toggle_user_active',
    'admin.invite_user',
    'admin.bulk_action_users',
    'admin.send_user_message',
    'admin.change_user_active_trail',
    'admin.list_tutors',
    # PlatformConfig e Level são config GLOBAL legada (docs/DEBITOS.md #1) —
    # decisão pendente de consolidação dos sistemas de nível
    'admin.list_levels',
    'admin.replace_levels',
    'admin.get_admin_config',
    'admin.update_admin_config',
    'notifications.get_public_config',
    'notifications.get_gamification_config',
    # flag global User.onboarding_completed (docs/DEBITOS.md #14)
    'onboarding.onboarding_status',
    # upload bruto de arquivo (sem linha de domínio; o REGISTRO do material é
    # tenant-scoped e o serve verifica acesso via material)
    'upload_file',
}
