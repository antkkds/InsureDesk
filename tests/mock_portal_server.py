"""Mock Insurance Portal — enhanced HTTP server for E2E testing.

Supports:
- Login with validation (error on wrong password)
- Delayed responses (loading states)
- Policy search with pagination
- Empty states (no results, no claims)
- Error states (session expired, not found)
- Modal dialogs (confirm/cancel)
"""

import json
import os
import threading
import socketserver
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

MOCK_DIR = Path(__file__).resolve().parent


class MockPortalHandler(BaseHTTPRequestHandler):
    """HTTP handler for mock portal with dynamic behaviors."""

    def log_message(self, format, *args):
        pass  # Suppress logs

    def _send_html(self, html, delay=0):
        if delay > 0:
            time.sleep(delay / 1000.0)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Set-Cookie", "mock_session=abc123; Path=/")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _read_params(self):
        return parse_qs(urlparse(self.path).query)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/index.html"
        params = parse_qs(parsed.query)
        delay = int(params.get("delay", [0])[0])
        error = params.get("error", [""])[0]
        empty = params.get("empty", [""])[0]
        page = int(params.get("page", [1])[0])

        if path == "/index.html" or path == "/login":
            self._handle_login_page(error, delay)
        elif path == "/dashboard.html":
            self._handle_dashboard(delay)
        elif path == "/search.html":
            self._handle_search(empty, page, delay)
        elif path == "/policy.html":
            self._handle_policy_detail(error, delay)
        elif path == "/claims.html":
            self._handle_claims(empty, delay)
        elif path == "/documents.html":
            self._handle_documents(delay)
        elif path == "/logout":
            self._handle_logout()
        elif path == "/api/search":
            self._handle_api_search(empty, page, delay)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len else ""

        if parsed.path == "/login":
            self._handle_login_post(body)
        elif parsed.path == "/api/claim":
            self._handle_claim_submit()
        else:
            self.send_error(404)

    # ── Pages ──

    def _handle_login_page(self, error="", delay=0):
        error_html = ""
        if error == "wrong_password":
            error_html = '<div class="error-message" style="color:red;margin-bottom:12px;">Invalid username or password. Please try again.</div>'
        elif error == "session_expired":
            error_html = '<div class="error-message" style="color:red;margin-bottom:12px;">Your session has expired. Please log in again.</div>'

        html = f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Mock Portal — Login</title>
<style>
body{{font-family:Arial;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}}
.login-box{{background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1);width:360px}}
h2{{margin-top:0;color:#1a1a2e}}
label{{display:block;margin:12px 0 4px;font-size:14px;color:#555}}
input{{width:100%;padding:10px;border:1px solid #ddd;border-radius:4px;box-sizing:border-box}}
input:focus{{border-color:#0066cc;outline:none}}
.checkbox-row{{display:flex;align-items:center;gap:8px;margin:12px 0}}
.checkbox-row input{{width:auto}}
button{{width:100%;padding:12px;background:#0066cc;color:white;border:none;border-radius:4px;font-size:16px;cursor:pointer}}
button:hover{{background:#0052a3}}
button:disabled{{background:#ccc;cursor:not-allowed}}
.spinner{{display:none;text-align:center;margin:12px 0}}
.spinner.active{{display:block}}
.error-message{{color:red;font-size:14px;margin-bottom:12px;padding:8px;background:#fff0f0;border-radius:4px}}
</style></head><body>
<div class="login-box">
<h2>i-Connect Portal Login</h2>
{error_html}
<form id="login-form" method="POST" action="/login" onsubmit="return handleLogin()">
<label for="username">Username / Email</label>
<input type="text" id="username" name="username" placeholder="Enter username" required />
<label for="password">Password</label>
<input type="password" id="password" name="password" placeholder="Enter password" required />
<div class="checkbox-row">
<input type="checkbox" id="remember" name="remember" />
<label for="remember" style="margin:0">Remember me</label>
</div>
<div class="spinner" id="login-spinner">⏳ Logging in...</div>
<button type="submit" id="login-btn">Sign In</button>
</form>
</div>
<script>
function handleLogin(){{
var btn=document.getElementById('login-btn');
var spinner=document.getElementById('login-spinner');
btn.disabled=true;
spinner.className='spinner active';
var pw=document.getElementById('password').value;
if(pw==='wrong'){{setTimeout(function(){{window.location.href='/index.html?error=wrong_password'}},1000);return false;}}
setTimeout(function(){{window.location.href='/dashboard.html'}},800);
return false;
}}
</script>
</body></html>"""
        self._send_html(html, delay)

    def _handle_dashboard(self, delay=0):
        html = """<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Mock Portal — Dashboard</title>
<style>
body{font-family:Arial;margin:0;background:#f0f2f5}
nav{background:#1a1a2e;color:white;padding:12px 24px;display:flex;align-items:center;gap:24px}
nav a{color:#ccc;text-decoration:none;font-size:14px;padding:6px 12px;border-radius:4px}
nav a:hover{color:white;background:rgba(255,255,255,0.1)}
.user-info{margin-left:auto;display:flex;align-items:center;gap:12px}
.user-profile-name{font-size:14px;color:#ccc}
.welcome-message{font-size:24px;color:#1a1a2e;margin:24px}
.content{padding:24px}
.card{background:white;padding:20px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.1);margin-bottom:16px}
.spinner{text-align:center;padding:40px;color:#999}
</style></head><body>
<nav>
<strong>Mock Portal</strong>
<a href="/dashboard.html">Dashboard</a>
<a href="/search.html">Policy</a>
<a href="/claims.html">Claims</a>
<a href="/documents.html">Documents</a>
<div class="user-info">
<span class="user-profile-name">Anthony Chong</span>
<a href="/logout" style="color:#999;">Logout</a>
</div>
</nav>
<div class="spinner" id="loading" style="display:none;">⏳ Loading dashboard...</div>
<div id="dashboard-content">
<div class="welcome-message">Welcome back, Anthony Chong</div>
<div class="content">
<div class="card"><h3>My Policies</h3><p>You have <strong>3 active policies</strong>.</p></div>
<div class="card"><h3>Recent Claims</h3><p>No recent claims found.</p></div>
</div></div>
<script>
var loading=document.getElementById('loading');
var content=document.getElementById('dashboard-content');
loading.style.display='block';
content.style.display='none';
setTimeout(function(){loading.style.display='none';content.style.display='block';},600);
</script></body></html>"""
        self._send_html(html, delay)

    def _handle_search(self, empty="", page=1, delay=0):
        empty_html = '<div class="empty-state" style="text-align:center;padding:40px;color:#999;">No policies found matching your search criteria.</div>' if empty else ""
        results_html = ""
        if not empty:
            if page == 1:
                results_html = """<table><thead><tr><th>Policy No</th><th>Type</th><th>Status</th><th>Premium</th></tr></thead><tbody>
<tr class="policy-row" onclick="location.href='/policy.html'"><td>GE-2024-001234</td><td>Fire Insurance</td><td>Active</td><td>RM 2,450.00</td></tr>
<tr class="policy-row" onclick="location.href='/policy.html'"><td>GE-2024-001235</td><td>Fire Insurance</td><td>Active</td><td>RM 3,200.00</td></tr>
<tr class="policy-row" onclick="location.href='/policy.html'"><td>GE-2024-001236</td><td>Motor Insurance</td><td>Active</td><td>RM 1,850.00</td></tr>
</tbody></table>"""
            elif page == 2:
                results_html = """<table><thead><tr><th>Policy No</th><th>Type</th><th>Status</th><th>Premium</th></tr></thead><tbody>
<tr class="policy-row" onclick="location.href='/policy.html'"><td>GE-2024-001237</td><td>Motor Insurance</td><td>Active</td><td>RM 2,100.00</td></tr>
<tr class="policy-row" onclick="location.href='/policy.html'"><td>GE-2024-001238</td><td>Travel Insurance</td><td>Expired</td><td>RM 350.00</td></tr>
</tbody></table>"""

        pagination = ""
        if not empty:
            pagination = """<div class="pagination" style="margin-top:16px;display:flex;gap:8px;">
<span class="page-indicator" style="color:#666;">Page """ + str(page) + """ of 2</span>
""" + ("""<a href="/search.html?page=1" class="page-link" style="padding:4px 10px;background:#0066cc;color:white;border-radius:4px;text-decoration:none;">&laquo; Previous</a>""" if page > 1 else "") + \
"""<a href="/search.html?page=2" class="page-link" style="padding:4px 10px;background:#0066cc;color:white;border-radius:4px;text-decoration:none;">Next &raquo;</a>
</div>"""

        html = f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Mock Portal — Policy Search</title>
<style>
body{{font-family:Arial;margin:0;background:#f0f2f5}}
nav{{background:#1a1a2e;color:white;padding:12px 24px;display:flex;align-items:center;gap:24px}}
nav a{{color:#ccc;text-decoration:none;font-size:14px;padding:6px 12px;border-radius:4px}}
.user-info{{margin-left:auto;display:flex;align-items:center;gap:12px}}
.user-profile-name{{font-size:14px;color:#ccc}}
.content{{padding:24px}}
.search-box{{background:white;padding:20px;border-radius:8px;display:flex;gap:12px;align-items:end;margin-bottom:16px}}
label{{display:block;font-size:13px;color:#555;margin-bottom:4px}}
input{{padding:8px 12px;border:1px solid #ddd;border-radius:4px;width:250px}}
button{{padding:8px 20px;background:#0066cc;color:white;border:none;border-radius:4px;cursor:pointer}}
.results-area{{background:white;padding:20px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.1)}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:10px;border-bottom:1px solid #eee}}
.policy-row{{cursor:pointer}}
.policy-row:hover{{background:#f5f8ff}}
.loading-indicator{{display:none;text-align:center;padding:20px;color:#999}}
</style></head><body>
<nav><strong>Mock Portal</strong>
<a href="/dashboard.html">Dashboard</a>
<a href="/search.html">Policy</a>
<a href="/claims.html">Claims</a>
<a href="/documents.html">Documents</a>
<div class="user-info"><span class="user-profile-name">Anthony Chong</span><a href="/logout" style="color:#999;">Logout</a></div></nav>
<div class="content"><h2>Policy Search</h2>
<div class="search-box">
<div><label for="policyNo">Policy Number</label><input type="text" id="policyNo" name="policyNo" placeholder="e.g. GE-2024-001234" /></div>
<button id="search-btn" onclick="doSearch()">Search</button>
</div>
<div class="loading-indicator" id="loading">⏳ Searching policies...</div>
<div class="results-area" id="results">
{empty_html}
{results_html}
{pagination}
</div></div>
<script>
function doSearch(){{
var loading=document.getElementById('loading');
var results=document.getElementById('results');
loading.style.display='block';
results.style.display='none';
setTimeout(function(){{
var no=document.getElementById('policyNo').value;
if(!no||no==='EMPTY'){{window.location.href='/search.html?empty=true';return;}}
window.location.href='/search.html?page=1';
}},800);
}}
</script></body></html>"""
        self._send_html(html, delay)

    def _handle_policy_detail(self, error="", delay=0):
        if error == "not_found":
            html = """<!DOCTYPE html><html><head><title>Error</title></head><body>
<div class="error-state" style="padding:40px;text-align:center;">
<h2>Policy Not Found</h2>
<p style="color:#999;">The policy you are looking for could not be found. It may have been cancelled or expired.</p>
<a href="/search.html">Back to Search</a>
</div></body></html>"""
        else:
            html = """<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Mock Portal — Policy Details</title>
<style>
body{font-family:Arial;margin:0;background:#f0f2f5}
nav{background:#1a1a2e;color:white;padding:12px 24px;display:flex;align-items:center;gap:24px}
nav a{color:#ccc;text-decoration:none;font-size:14px;padding:6px 12px;border-radius:4px}
.user-info{margin-left:auto;display:flex;align-items:center;gap:12px}
.user-profile-name{font-size:14px;color:#ccc}
.content{padding:24px;max-width:800px}
.card{background:white;padding:24px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.1)}
.policy-number{font-size:18px;font-weight:bold;color:#1a1a2e}
.policy-status{display:inline-block;padding:4px 12px;border-radius:12px;background:#d4edda;color:#155724;font-size:13px}
.premium-amount{font-size:24px;color:#0066cc;font-weight:bold}
.detail-row{display:flex;padding:8px 0;border-bottom:1px solid #f0f0f0}
.detail-label{width:160px;color:#777;font-size:14px}
.detail-value{flex:1;font-weight:500}
button{padding:10px 24px;background:#0066cc;color:white;border:none;border-radius:4px;cursor:pointer;margin-top:16px}
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000}
.modal-box{background:white;padding:24px;border-radius:8px;width:400px;margin:200px auto;box-shadow:0 4px 20px rgba(0,0,0,0.2)}
.modal-box h3{margin-top:0}
.modal-actions{display:flex;gap:8px;justify-content:end;margin-top:16px}
</style></head><body>
<nav><strong>Mock Portal</strong>
<a href="/dashboard.html">Dashboard</a>
<a href="/search.html">Policy</a>
<a href="/claims.html">Claims</a>
<a href="/documents.html">Documents</a>
<div class="user-info"><span class="user-profile-name">Anthony Chong</span><a href="/logout" style="color:#999;">Logout</a></div></nav>
<div class="content"><div class="card">
<div class="policy-number">GE-2024-001234</div>
<span class="policy-status">Active</span>
<div class="detail-row"><span class="detail-label">Premium</span><span class="premium-amount">RM 2,450.00</span></div>
<div class="detail-row"><span class="detail-label">Start Date</span><span class="start-date">01/03/2024</span></div>
<div class="detail-row"><span class="detail-label">End Date</span><span class="expiry-date">28/02/2025</span></div>
<div class="coverage-details" style="margin-top:16px;"><h3>Coverage Details</h3><ul>
<li>Fire & Lightning</li><li>Explosion</li><li>Flood & Typhoon</li>
</ul></div>
<button id="download-btn" onclick="showModal()">Download PDF</button>
</div></div>

<div class="modal-overlay" id="confirm-modal">
<div class="modal-box">
<h3>Confirm Download</h3>
<p>Are you sure you want to download the policy document?</p>
<div class="modal-actions">
<button id="modal-cancel" onclick="hideModal()" style="background:#6c757d">Cancel</button>
<button id="modal-confirm" onclick="doDownload()" style="background:#28a745">Confirm</button>
</div></div></div>

<script>
function showModal(){document.getElementById('confirm-modal').style.display='block';}
function hideModal(){document.getElementById('confirm-modal').style.display='none';}
function doDownload(){alert('Downloading...');hideModal();}
</script></body></html>"""
        self._send_html(html, delay)

    def _handle_claims(self, empty="", delay=0):
        claims_html = '<div class="empty-state" style="text-align:center;padding:40px;color:#999;">You have no claims history.</div>' if empty else """
<span class="claim-status" style="display:inline-block;padding:4px 12px;border-radius:12px;background:#fff3cd;color:#856404;font-size:13px;">Pending Review</span>
<p style="margin-top:12px;font-size:14px;color:#666;">Claim CL-2023-089 — Submitted on 15/11/2023</p>"""

        html = f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Mock Portal — Claims</title>
<style>
body{{font-family:Arial;margin:0;background:#f0f2f5}}
nav{{background:#1a1a2e;color:white;padding:12px 24px;display:flex;align-items:center;gap:24px}}
nav a{{color:#ccc;text-decoration:none;font-size:14px;padding:6px 12px;border-radius:4px}}
.user-info{{margin-left:auto;display:flex;align-items:center;gap:12px}}
.user-profile-name{{font-size:14px;color:#ccc}}
.content{{padding:24px;max-width:700px}}
.card{{background:white;padding:24px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.1);margin-bottom:16px}}
label{{display:block;font-size:14px;color:#555;margin:12px 0 4px}}
input,select,textarea{{width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:4px;box-sizing:border-box;font-size:14px}}
textarea{{height:80px}}
button{{padding:10px 24px;border:none;border-radius:4px;cursor:pointer;margin-top:16px;margin-right:8px}}
.btn-primary{{background:#0066cc;color:white}}
.btn-primary:hover{{background:#0052a3}}
.success-message{{display:none;background:#d4edda;color:#155724;padding:12px;border-radius:4px;margin-bottom:16px}}
.loading-indicator{{display:none;text-align:center;padding:12px;color:#999}}
</style></head><body>
<nav><strong>Mock Portal</strong>
<a href="/dashboard.html">Dashboard</a>
<a href="/search.html">Policy</a>
<a href="/claims.html">Claims</a>
<a href="/documents.html">Documents</a>
<div class="user-info"><span class="user-profile-name">Anthony Chong</span><a href="/logout" style="color:#999;">Logout</a></div></nav>
<div class="content"><h2>Submit a Claim</h2>
<div class="success-message" id="success">Your claim has been submitted. Reference: CL-2024-001</div>
<div class="card">
<form id="claim-form" onsubmit="return submitClaim()">
<label for="policyNo">Policy Number</label>
<input type="text" id="policyNo" name="policyNo" value="GE-2024-001234" />
<label for="incidentDate">Incident Date</label>
<input type="date" id="incidentDate" name="incidentDate" />
<label for="claimType">Claim Type</label>
<select id="claimType" name="claimType">
<option value="">Select type...</option>
<option value="fire">Fire Damage</option>
<option value="flood">Flood Damage</option>
<option value="theft">Theft</option>
<option value="other">Other</option>
</select>
<label for="description">Description</label>
<textarea id="description" name="description" placeholder="Describe the incident..."></textarea>
<div class="loading-indicator" id="claim-loading">⏳ Submitting claim...</div>
<button type="submit" class="btn-primary" id="submit-claim-btn">Submit Claim</button>
</form></div>
<div class="card"><h3>Your Claims</h3>{claims_html}</div></div>
<script>
function submitClaim(){{
var btn=document.getElementById('submit-claim-btn');
var loading=document.getElementById('claim-loading');
var success=document.getElementById('success');
btn.disabled=true;
loading.style.display='block';
setTimeout(function(){{
loading.style.display='none';
success.style.display='block';
btn.disabled=false;
}},1000);
return false;
}}
</script></body></html>"""
        self._send_html(html, delay)

    def _handle_documents(self, delay=0):
        html = """<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>Mock Portal — Documents</title>
<style>
body{font-family:Arial;margin:0;background:#f0f2f5}
nav{background:#1a1a2e;color:white;padding:12px 24px;display:flex;align-items:center;gap:24px}
nav a{color:#ccc;text-decoration:none;font-size:14px;padding:6px 12px;border-radius:4px}
.user-info{margin-left:auto;display:flex;align-items:center;gap:12px}
.user-profile-name{font-size:14px;color:#ccc}
.content{padding:24px;max-width:700px}
.card{background:white;padding:24px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.1);margin-bottom:16px}
</style></head><body>
<nav><strong>Mock Portal</strong>
<a href="/dashboard.html">Dashboard</a>
<a href="/search.html">Policy</a>
<a href="/claims.html">Claims</a>
<a href="/documents.html">Documents</a>
<div class="user-info"><span class="user-profile-name">Anthony Chong</span><a href="/logout" style="color:#999;">Logout</a></div></nav>
<div class="content"><h2>Documents</h2>
<div class="card"><h3>Upload Document</h3><input type="file" name="document" /></div>
<div class="card"><h3>My Documents</h3>
<ul style="list-style:none;padding:0;">
<li style="padding:8px 0;border-bottom:1px solid #f0f0f0;">Policy Schedule — GE-2024-001234.pdf</li>
<li style="padding:8px 0;border-bottom:1px solid #f0f0f0;">Claim Report — CL-2023-089.pdf</li>
</ul></div></div></body></html>"""
        self._send_html(html, delay)

    def _handle_logout(self):
        self.send_response(302)
        self.send_header("Location", "/index.html")
        self.end_headers()

    def _handle_login_post(self, body):
        """Handle login form POST submission."""
        params = parse_qs(body)
        password = params.get("password", [""])[0]
        if password == "wrong":
            self.send_response(302)
            self.send_header("Location", "/index.html?error=wrong_password")
            self.end_headers()
        else:
            self.send_response(302)
            self.send_header("Location", "/dashboard.html")
            self.end_headers()

    def _handle_api_search(self, empty="", page=1, delay=0):
        if delay > 0:
            time.sleep(delay / 1000.0)
        if empty:
            self._send_json({"results": [], "total": 0, "page": page})
        else:
            self._send_json({
                "results": [
                    {"policy_no": f"GE-2024-{1000 + page * 10 + i:06d}",
                     "type": "Fire Insurance",
                     "status": "Active",
                     "premium": f"RM {2000 + i * 250:.2f}"}
                    for i in range(10)
                ],
                "total": 22,
                "page": page,
                "total_pages": 3,
            })

    def _handle_claim_submit(self):
        self._send_json({"status": "success", "reference": "CL-2024-001"})


class MockPortalServer:
    """Enhanced mock portal server with dynamic behaviors."""

    def __init__(self):
        self.port = None
        self._server = None
        self._thread = None

    def start(self):
        os.chdir(str(MOCK_DIR))
        self._server = socketserver.TCPServer(("127.0.0.1", 0), MockPortalHandler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()


if __name__ == "__main__":
    server = MockPortalServer()
    port = server.start()
    print(f"Mock portal running on http://127.0.0.1:{port}")
    print(f"  Login:    http://127.0.0.1:{port}/index.html")
    print(f"  Dashboard: http://127.0.0.1:{port}/dashboard.html")
    print(f"  Search:   http://127.0.0.1:{port}/search.html")
    print(f"  Claims:   http://127.0.0.1:{port}/claims.html")
    print(f"  Wrong pw: http://127.0.0.1:{port}/index.html?error=wrong_password")
    print(f"  Empty:    http://127.0.0.1:{port}/search.html?empty=true")
    print(f"  Delay:    http://127.0.0.1:{port}/dashboard.html?delay=2000")
    print("Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
