from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import json
import uuid
import random
import os
import hashlib
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

DB_PATH = '/tmp/tracker.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table des utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE,
            ip TEXT,
            user_agent TEXT,
            first_seen TEXT,
            last_seen TEXT,
            visit_count INTEGER DEFAULT 1,
            screen_width INTEGER,
            screen_height INTEGER,
            device_pixel_ratio REAL,
            platform TEXT,
            language TEXT,
            country TEXT,
            city TEXT
        )
    ''')
    
    # Table des tentatives de concours
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contest_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            email TEXT,
            phone TEXT,
            name TEXT,
            timestamp TEXT,
            is_winner BOOLEAN DEFAULT 0,
            prize TEXT
        )
    ''')
    
    # Table des logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            action TEXT,
            data TEXT,
            timestamp TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de données initialisée")

def get_geolocation(ip):
    """Simule la géolocalisation (optionnel)"""
    # En production, utiliser une API comme ip-api.com
    return {"country": "France", "city": "Paris"}

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/admin')
def serve_admin():
    return send_from_directory('.', 'admin.html')

@app.route('/api/collect', methods=['POST'])
def collect_data():
    try:
        data = request.get_json()
        user_uuid = data.get('uuid', str(uuid.uuid4()))
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Ajout ou mise à jour de l'utilisateur
        cursor.execute('''
            INSERT INTO users (uuid, ip, user_agent, first_seen, last_seen, 
                              screen_width, screen_height, device_pixel_ratio, platform, language)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uuid) DO UPDATE SET
                last_seen = ?,
                visit_count = visit_count + 1
        ''', (user_uuid, ip, data.get('user_agent'), datetime.now().isoformat(), datetime.now().isoformat(),
              data.get('sw5', 0), data.get('sh5', 0), data.get('device_pixel_ratio', 1),
              data.get('platform', ''), data.get('language', ''),
              datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'ok', 'uuid': user_uuid})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/contest/enter', methods=['POST'])
def contest_entry():
    """Inscription au concours"""
    try:
        data = request.get_json()
        user_uuid = data.get('uuid')
        email = data.get('email')
        phone = data.get('phone')
        name = data.get('name')
        
        # Vérification si déjà participé
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM contest_attempts WHERE uuid = ? OR email = ?', (user_uuid, email))
        existing = cursor.fetchone()[0]
        
        if existing > 0:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Vous avez déjà participé !'}), 400
        
        # Tirage au sort (1 chance sur 1000 de gagner)
        is_winner = random.randint(1, 1000) == 1
        prize = "iPhone 15 Pro" if is_winner else None
        
        cursor.execute('''
            INSERT INTO contest_attempts (uuid, email, phone, name, timestamp, is_winner, prize)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_uuid, email, phone, name, datetime.now().isoformat(), is_winner, prize))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'ok',
            'is_winner': is_winner,
            'prize': prize,
            'message': 'Félicitations ! Vous avez gagné !' if is_winner else 'Bonne chance !'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    """Stats pour l'admin (protégé par clé)"""
    api_key = request.headers.get('X-API-Key')
    
    if api_key != 'arcane@M12':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Stats globales
    cursor.execute('SELECT COUNT(*) FROM users')
    total_visitors = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM contest_attempts')
    total_participants = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM contest_attempts WHERE is_winner = 1')
    total_winners = cursor.fetchone()[0]
    
    # Derniers participants
    cursor.execute('SELECT name, email, phone, timestamp, is_winner, prize FROM contest_attempts ORDER BY id DESC LIMIT 50')
    participants = cursor.fetchall()
    
    # Derniers visiteurs
    cursor.execute('SELECT uuid, user_agent, screen_width, screen_height, platform, last_seen FROM users ORDER BY id DESC LIMIT 30')
    visitors = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'stats': {
            'total_visitors': total_visitors,
            'total_participants': total_participants,
            'total_winners': total_winners,
            'conversion_rate': round((total_participants / total_visitors * 100), 2) if total_visitors > 0 else 0
        },
        'participants': [{'name': p[0], 'email': p[1], 'phone': p[2], 'date': p[3], 'winner': p[4], 'prize': p[5]} for p in participants],
        'visitors': [{'uuid': v[0][:8] + '...', 'device': v[1][:50], 'screen': f"{v[2]}x{v[3]}", 'platform': v[4], 'last_seen': v[5]} for v in visitors]
    })

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
