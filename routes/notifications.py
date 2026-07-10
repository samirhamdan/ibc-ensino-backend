"""
User-facing notification and announcement routes
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from extensions import db
from core.tenancy import current_tenant_id, get_scoped_or_404, role_no_tenant
from models import Notification, Announcement, AnnouncementDismissal, User, PlatformConfig, Level

notifications_bp = Blueprint('notifications', __name__)


def _current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


@notifications_bp.route('/notifications', methods=['GET'])
def list_notifications():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    query = Notification.query.filter_by(tenant_id=current_tenant_id(), user_id=user.id)
    if request.args.get('unread_only') == 'true':
        query = query.filter_by(is_read=False)
    notifications = query.order_by(Notification.created_at.desc()).all()
    unread_count = Notification.query.filter_by(tenant_id=current_tenant_id(), user_id=user.id, is_read=False).count()

    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count,
    }), 200


@notifications_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    n = Notification.query.filter_by(tenant_id=current_tenant_id(), id=notification_id, user_id=user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({'ok': True}), 200


@notifications_bp.route('/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Notification.query.filter_by(tenant_id=current_tenant_id(), user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True}), 200


@notifications_bp.route('/announcements/active', methods=['GET'])
def list_active_announcements():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    now = datetime.utcnow()
    dismissed_ids = {
        d.announcement_id for d in AnnouncementDismissal.query.filter_by(tenant_id=current_tenant_id(), user_id=user.id).all()
    }

    announcements = Announcement.query.filter(Announcement.tenant_id == current_tenant_id(), 
        Announcement.is_active == True,
        Announcement.target_role.in_([role_no_tenant(user), 'all']),
    ).order_by(Announcement.created_at.desc()).all()

    result = []
    for a in announcements:
        if a.id in dismissed_ids:
            continue
        if a.expires_at and a.expires_at < now:
            continue
        result.append(a.to_dict())

    return jsonify(result), 200


@notifications_bp.route('/announcements/<int:announcement_id>/dismiss', methods=['POST'])
def dismiss_announcement(announcement_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    get_scoped_or_404(Announcement, announcement_id)
    existing = AnnouncementDismissal.query.filter_by(tenant_id=current_tenant_id(), 
        user_id=user.id, announcement_id=announcement_id
    ).first()
    if not existing:
        db.session.add(AnnouncementDismissal(user_id=user.id, announcement_id=announcement_id))
        db.session.commit()
    return jsonify({'ok': True}), 200


def _get_or_create_config():
    config = PlatformConfig.query.first()
    if not config:
        config = PlatformConfig()
        db.session.add(config)
        db.session.commit()
    return config


@notifications_bp.route('/config/public', methods=['GET'])
def get_public_config():
    config = _get_or_create_config()
    return jsonify({
        'platform_name': config.platform_name,
        'platform_short': config.platform_short,
        'whatsapp': config.whatsapp,
        'support_email': config.support_email,
        'verse_text': config.verse_text,
        'verse_reference': config.verse_reference,
    }), 200


@notifications_bp.route('/config/gamification', methods=['GET'])
def get_gamification_config():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    config = _get_or_create_config()
    levels = Level.query.order_by(Level.number).all()
    return jsonify({
        'points_read_material': config.points_read_material,
        'points_complete_video': config.points_complete_video,
        'points_correct_exercise': config.points_correct_exercise,
        'points_complete_course': config.points_complete_course,
        'points_complete_trail': config.points_complete_trail,
        'levels': [lv.to_dict() for lv in levels],
    }), 200
