from flask import Flask, render_template, request, jsonify
import requests
import os
from datetime import datetime, timedelta

app = Flask(__name__)
API_KEY = os.environ.get('YOUTUBE_API_KEY', '') or 'BURAYA_KEY'

BASE_URL = 'https://www.googleapis.com/youtube/v3'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trending')
def trending():
    """Türkiye ve dünyada trend olan videolar"""
    region = request.args.get('region', 'TR')
    category = request.args.get('category', '0')  # 0 = hepsi
    max_results = request.args.get('limit', '20')

    params = {
        'part': 'snippet,statistics,contentDetails',
        'chart': 'mostPopular',
        'regionCode': region,
        'maxResults': max_results,
        'key': API_KEY
    }
    if category != '0':
        params['videoCategoryId'] = category

    resp = requests.get(f'{BASE_URL}/videos', params=params)
    data = resp.json()

    # Hata varsa göster
    if 'error' in data:
        return jsonify({'api_error': data['error']['message'], 'code': data['error']['code']}), 400

    videos = []
    for item in data.get('items', []):
        snippet = item['snippet']
        stats = item.get('statistics', {})

        # Yayın tarihinden bu yana geçen süre
        published = datetime.strptime(snippet['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
        hours_since = max((datetime.utcnow() - published).total_seconds() / 3600, 1)

        view_count = int(stats.get('viewCount', 0))
        like_count = int(stats.get('likeCount', 0))
        comment_count = int(stats.get('commentCount', 0))

        # Viral skor: izlenme/saat + etkileşim oranı
        views_per_hour = view_count / hours_since
        engagement = ((like_count + comment_count) / max(view_count, 1)) * 100

        videos.append({
            'id': item['id'],
            'title': snippet['title'],
            'channel': snippet['channelTitle'],
            'channelId': snippet.get('channelId', ''),
            'thumbnail': snippet['thumbnails']['high']['url'],
            'publishedAt': snippet['publishedAt'],
            'hoursSince': round(hours_since, 1),
            'viewCount': view_count,
            'likeCount': like_count,
            'commentCount': comment_count,
            'viewsPerHour': round(views_per_hour),
            'engagement': round(engagement, 2),
            'viralScore': round((views_per_hour * 0.7) + (engagement * 1000 * 0.3)),
            'category': snippet.get('categoryId', '0')
        })

    # Viral skora göre sırala
    videos.sort(key=lambda x: x['viralScore'], reverse=True)
    return jsonify(videos)

@app.route('/api/video/<video_id>')
def video_detail(video_id):
    """Tek bir videonun detaylı analizi"""
    params = {
        'part': 'snippet,statistics,contentDetails,topicDetails',
        'id': video_id,
        'key': API_KEY
    }
    resp = requests.get(f'{BASE_URL}/videos', params=params)
    data = resp.json()

    if not data.get('items'):
        return jsonify({'error': 'Video bulunamadı'}), 404

    item = data['items'][0]
    snippet = item['snippet']
    stats = item.get('statistics', {})

    published = datetime.strptime(snippet['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
    hours_since = max((datetime.utcnow() - published).total_seconds() / 3600, 1)
    days_since = hours_since / 24

    view_count = int(stats.get('viewCount', 0))
    like_count = int(stats.get('likeCount', 0))
    comment_count = int(stats.get('commentCount', 0))

    views_per_hour = view_count / hours_since
    views_per_day = view_count / max(days_since, 1)
    engagement = ((like_count + comment_count) / max(view_count, 1)) * 100
    like_ratio = (like_count / max(view_count, 1)) * 100

    # Kanal bilgisi
    channel_params = {
        'part': 'statistics,snippet',
        'id': snippet['channelId'],
        'key': API_KEY
    }
    ch_resp = requests.get(f'{BASE_URL}/channels', params=channel_params)
    ch_data = ch_resp.json()
    channel_info = {}
    if ch_data.get('items'):
        ch = ch_data['items'][0]
        ch_stats = ch.get('statistics', {})
        channel_info = {
            'name': ch['snippet']['title'],
            'subscribers': int(ch_stats.get('subscriberCount', 0)),
            'totalViews': int(ch_stats.get('viewCount', 0)),
            'videoCount': int(ch_stats.get('videoCount', 0)),
            'thumbnail': ch['snippet']['thumbnails']['default']['url']
        }

    return jsonify({
        'id': item['id'],
        'title': snippet['title'],
        'description': snippet.get('description', '')[:500],
        'channel': snippet['channelTitle'],
        'channelId': snippet['channelId'],
        'channelInfo': channel_info,
        'thumbnail': snippet['thumbnails']['high']['url'],
        'publishedAt': snippet['publishedAt'],
        'hoursSince': round(hours_since, 1),
        'daysSince': round(days_since, 1),
        'viewCount': view_count,
        'likeCount': like_count,
        'commentCount': comment_count,
        'viewsPerHour': round(views_per_hour),
        'viewsPerDay': round(views_per_day),
        'engagement': round(engagement, 2),
        'likeRatio': round(like_ratio, 2),
        'viralScore': round((views_per_hour * 0.7) + (engagement * 1000 * 0.3)),
        'tags': snippet.get('tags', [])[:15]
    })

@app.route('/api/search')
def search_viral():
    """Anahtar kelimeyle viral içerik ara"""
    query = request.args.get('q', '')
    order = request.args.get('order', 'viewCount')
    published_after = request.args.get('after', '')

    if not query:
        return jsonify([])

    params = {
        'part': 'snippet',
        'q': query,
        'type': 'video',
        'order': order,
        'maxResults': '15',
        'key': API_KEY
    }

    if published_after:
        days = int(published_after)
        after_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        params['publishedAfter'] = after_date

    resp = requests.get(f'{BASE_URL}/search', params=params)
    data = resp.json()

    video_ids = [item['id']['videoId'] for item in data.get('items', []) if item['id'].get('videoId')]

    if not video_ids:
        return jsonify([])

    # Video detaylarını al
    vid_params = {
        'part': 'snippet,statistics',
        'id': ','.join(video_ids),
        'key': API_KEY
    }
    vid_resp = requests.get(f'{BASE_URL}/videos', params=vid_params)
    vid_data = vid_resp.json()

    videos = []
    for item in vid_data.get('items', []):
        snippet = item['snippet']
        stats = item.get('statistics', {})

        published = datetime.strptime(snippet['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
        hours_since = max((datetime.utcnow() - published).total_seconds() / 3600, 1)

        view_count = int(stats.get('viewCount', 0))
        like_count = int(stats.get('likeCount', 0))
        comment_count = int(stats.get('commentCount', 0))

        views_per_hour = view_count / hours_since
        engagement = ((like_count + comment_count) / max(view_count, 1)) * 100

        videos.append({
            'id': item['id'],
            'title': snippet['title'],
            'channel': snippet['channelTitle'],
            'thumbnail': snippet['thumbnails']['high']['url'],
            'publishedAt': snippet['publishedAt'],
            'hoursSince': round(hours_since, 1),
            'viewCount': view_count,
            'likeCount': like_count,
            'commentCount': comment_count,
            'viewsPerHour': round(views_per_hour),
            'engagement': round(engagement, 2),
            'viralScore': round((views_per_hour * 0.7) + (engagement * 1000 * 0.3))
        })

    videos.sort(key=lambda x: x['viralScore'], reverse=True)
    return jsonify(videos)

@app.route('/api/compare')
def compare_videos():
    """Birden fazla videoyu karşılaştır"""
    ids = request.args.get('ids', '')
    if not ids:
        return jsonify([])

    params = {
        'part': 'snippet,statistics',
        'id': ids,
        'key': API_KEY
    }
    resp = requests.get(f'{BASE_URL}/videos', params=params)
    data = resp.json()

    videos = []
    for item in data.get('items', []):
        snippet = item['snippet']
        stats = item.get('statistics', {})

        published = datetime.strptime(snippet['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
        hours_since = max((datetime.utcnow() - published).total_seconds() / 3600, 1)

        view_count = int(stats.get('viewCount', 0))
        like_count = int(stats.get('likeCount', 0))
        comment_count = int(stats.get('commentCount', 0))
        views_per_hour = view_count / hours_since
        engagement = ((like_count + comment_count) / max(view_count, 1)) * 100

        videos.append({
            'id': item['id'],
            'title': snippet['title'],
            'channel': snippet['channelTitle'],
            'thumbnail': snippet['thumbnails']['high']['url'],
            'viewCount': view_count,
            'likeCount': like_count,
            'commentCount': comment_count,
            'viewsPerHour': round(views_per_hour),
            'engagement': round(engagement, 2),
            'viralScore': round((views_per_hour * 0.7) + (engagement * 1000 * 0.3))
        })

    return jsonify(videos)

if __name__ == '__main__':
    if not API_KEY:
        print("UYARI: YOUTUBE_API_KEY ayarlanmamis!")
        print("set YOUTUBE_API_KEY=senin_key_buraya")
    app.run(debug=True, port=5001)
