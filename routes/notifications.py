"""
User-facing notification and announcement routes
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from extensions import db
from models import Notification, Announcement, AnnouncementDismissal, User

notifications_bp = Blueprint('notifications', __name__)


def _current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


@notifications_bp.route('/notifications', methods=['GET'])
def list_notifications():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    query = Notification.query.filter_by(user_id=user.id)
    if request.args.get('unread_only') == 'true':
        query = query.filter_by(is_read=False)
    notifications = query.order_by(Notification.created_at.desc()).all()
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()

    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count,
    }), 200


@notifications_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    n = Notification.query.filter_by(id=notification_id, user_id=user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({'ok': True}), 200


@notifications_bp.route('/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True}), 200


@notifications_bp.route('/announcements/active', methods=['GET'])
def list_active_announcements():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    now = datetime.utcnow()
    dismissed_ids = {
        d.announcement_id for d in AnnouncementDismissal.query.filter_by(user_id=user.id).all()
    }

    announcements = Announcement.query.filter(
        Announcement.is_active == True,
        Announcement.target_role.in_([user.role, 'all']),
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

    Announcement.query.get_or_404(announcement_id)
    existing = AnnouncementDismissal.query.filter_by(
        user_id=user.id, announcement_id=announcement_id
    ).first()
    if not existing:
        db.session.add(AnnouncementDismissal(user_id=user.id, announcement_id=announcement_id))
        db.session.commit()
    return jsonify({'ok': True}), 200
