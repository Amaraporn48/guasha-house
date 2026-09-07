<?php
/**
 * Guasha House Diagnostics & Health Inspector
 */
header('Content-Type: text/html; charset=utf-8');

$dir = __DIR__;
$venv_python = "$dir/venv/bin/python";
$venv_exists = file_exists($venv_python);
$log_file = "$dir/uvicorn.log";
$log_content = file_exists($log_file) ? file_get_contents($log_file) : "No uvicorn.log found.";

$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.5);
$port_open = ($fp !== false);
if ($fp) fclose($fp);

$disabled_funcs = explode(',', (string)ini_get('disable_functions'));
$disabled_funcs = array_map('trim', $disabled_funcs);

?>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>🌿 Guasha House Server Diagnostics</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 30px; margin: 0; }
        .container { max-width: 800px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h1 { color: #38bdf8; margin-top: 0; font-size: 22px; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 13px; margin-left: 8px; }
        .badge-green { background: #16a34a; color: #fff; }
        .badge-red { background: #dc2626; color: #fff; }
        .badge-yellow { background: #ca8a04; color: #fff; }
        .item { padding: 12px 0; border-bottom: 1px solid #334155; }
        pre { background: #090d16; padding: 15px; border-radius: 8px; overflow-x: auto; color: #a5f3fc; font-size: 13px; }
        .btn { display: inline-block; padding: 8px 16px; background: #0284c7; color: #fff; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 10px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🌿 Guasha House Hostinger Diagnostics</h1>
    
    <div class="item">
        <strong>Backend Port 8000 Status:</strong>
        <?php if ($port_open): ?>
            <span class="badge badge-green">ONLINE (Port 8000 responding)</span>
        <?php else: ?>
            <span class="badge badge-red">OFFLINE (Port 8000 not responding)</span>
        <?php endif; ?>
    </div>

    <div class="item">
        <strong>Python VirtualEnv:</strong>
        <code><?= htmlspecialchars($venv_python) ?></code>
        <?php if ($venv_exists): ?>
            <span class="badge badge-green">EXISTS</span>
        <?php else: ?>
            <span class="badge badge-red">NOT FOUND</span>
        <?php endif; ?>
    </div>

    <div class="item">
        <strong>PHP Functions Status:</strong><br>
        <code>exec()</code>: <?= in_array('exec', $disabled_funcs) ? '<span class="badge badge-red">DISABLED</span>' : '<span class="badge badge-green">ENABLED</span>' ?> |
        <code>shell_exec()</code>: <?= in_array('shell_exec', $disabled_funcs) ? '<span class="badge badge-red">DISABLED</span>' : '<span class="badge badge-green">ENABLED</span>' ?> |
        <code>fsockopen()</code>: <?= in_array('fsockopen', $disabled_funcs) ? '<span class="badge badge-red">DISABLED</span>' : '<span class="badge badge-green">ENABLED</span>' ?> |
        <code>curl</code>: <?= extension_loaded('curl') ? '<span class="badge badge-green">ENABLED</span>' : '<span class="badge badge-red">MISSING</span>' ?>
    </div>

    <div class="item">
        <strong>Latest uvicorn.log Output:</strong>
        <pre><?= htmlspecialchars($log_content) ?></pre>
    </div>

    <div style="margin-top: 20px;">
        <a href="/" class="btn">กลับหน้าหลัก</a>
        <a href="/diag.php" class="btn" style="background: #475569;">รีเฟรชสถานะ</a>
    </div>
</div>
</body>
</html>
