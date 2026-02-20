import requests
import concurrent.futures
from flask import Flask, render_template, request, Response, jsonify

app = Flask(__name__)

# ================= 配置区 =================
# 如果你有 SteamGridDB API Key，填在这里。
# 如果留空字符串 ""，程序将自动只使用 Steam 官方搜索。
# 获取地址: https://www.steamgriddb.com/profile/preferences/api
SGDB_API_KEY = "2e2a1373495f419142d576b1aab7aa9f" 
# =========================================

# 伪装头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
}

@app.route('/')
def index():
    return render_template('index.html')

# --- 搜索功能 A: Steam 官方商店 ---
def search_steam_store(query):
    results = []
    try:
        url = "https://store.steampowered.com/api/storesearch/"
        params = {'term': query, 'l': 'schinese', 'cc': 'CN'}
        r = requests.get(url, params=params, headers=HEADERS, timeout=5)
        data = r.json()
        
        if data.get('total', 0) > 0:
            for item in data['items'][:3]: # 取前3个
                app_id = item['id']
                img_url = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_600x900_2x.jpg"
                results.append({
                    'name': f"[Steam] {item['name']}", # 标记来源
                    'url': img_url,
                    'source': 'steam'
                })
    except Exception as e:
        print(f"Steam Search Error: {e}")
    return results

# --- 搜索功能 B: SteamGridDB ---
def search_sgdb(query):
    results = []
    if not SGDB_API_KEY:
        return results

    try:
        auth_headers = {'Authorization': f'Bearer {SGDB_API_KEY}'}
        
        # 1. 搜 ID
        search_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{query}"
        r = requests.get(search_url, headers=auth_headers, timeout=5)
        data = r.json()
        
        if data['success'] and len(data['data']) > 0:
            game_id = data['data'][0]['id']
            game_name = data['data'][0]['name']
            
            # 2. 搜图
            grid_url = f"https://www.steamgriddb.com/api/v2/grids/game/{game_id}?dimensions=600x900&styles=alternate,material,white_logo"
            r_grid = requests.get(grid_url, headers=auth_headers, timeout=5)
            grid_data = r_grid.json()
            
            if grid_data['success']:
                for item in grid_data['data'][:4]: # 取前4张美图
                    results.append({
                        'name': f"[Art] {game_name}", # 标记来源
                        'url': item['url'],
                        'source': 'sgdb'
                    })
    except Exception as e:
        print(f"SGDB Search Error: {e}")
    return results

@app.route('/search', methods=['GET'])
def search_game():
    query = request.args.get('q')
    if not query:
        return jsonify([])

    final_results = []
    
    # 使用线程池并行搜索，速度更快
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_steam = executor.submit(search_steam_store, query)
        future_sgdb = executor.submit(search_sgdb, query)
        
        # 获取结果 (Steam 优先展示)
        final_results.extend(future_steam.result())
        final_results.extend(future_sgdb.result())

    return jsonify(final_results)

@app.route('/proxy_image')
def proxy_image():
    img_url = request.args.get('url')
    if not img_url: return "No URL", 404
    
    try:
        # 1. 请求原图
        resp = requests.get(img_url, headers=HEADERS, stream=True, timeout=10)
        
        # 2. [Steam专属逻辑] 智能降级防破图
        # 只有 Steam 的域名才执行这个逻辑，SGDB 的图通常不会 404
        if resp.status_code in [404, 403] and "akamai.steamstatic.com" in img_url:
            print(f"Steam竖图缺失，降级中: {img_url}")
            fallback_url = img_url.replace("library_600x900_2x.jpg", "header.jpg")
            fallback_url = fallback_url.replace("library_600x900.jpg", "header.jpg")
            resp = requests.get(fallback_url, headers=HEADERS, stream=True, timeout=10)

        if resp.status_code != 200: return "Image fail", 404

        # 3. 转发
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)

    except Exception as e:
        print(f"Proxy Error: {e}")
        return str(e), 500

if __name__ == '__main__':
    print("启动成功！双引擎搜索模式已就绪。")
    app.run(debug=True, port=5000)