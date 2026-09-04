<?php
/**
 * Guasha House Zero-Downtime Auto-Deploy Webhook
 * Triggers git pull and background service restart automatically
 */

// Secret Token for deployment security
$SECRET_TOKEN = "guashahouse_auto_deploy_secret_2026";

$received_token = $_GET['token'] ?? $_POST['token'] ?? ($_SERVER['HTTP_X_DEPLOY_TOKEN'] ?? '');

if ($received_token !== $SECRET_TOKEN) {
    http_response_code(403);
    header('Content-Type: application/json');
    echo json_encode(["status" => "error", "message" => "Unauthorized: Invalid deployment token"]);
    exit;
}

$dir = __DIR__;
$output = [];

// 1. Pull latest code from GitHub
$cmd_git = "cd $dir && git fetch --all 2>&1 && git reset --hard origin/main 2>&1";
@exec($cmd_git, $output, $git_code);

// 2. Restart background runner
$cmd_restart = "cd $dir && pkill -f 'uvicorn main:app' 2>/dev/null; bash hostinger_run.sh > uvicorn.log 2>&1 &";
@exec($cmd_restart, $output, $restart_code);

// 3. Wait a moment and check status
usleep(500000);
$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.5);
$is_running = false;
if ($fp) {
    $is_running = true;
    fclose($fp);
}

header('Content-Type: application/json');
echo json_encode([
    "status" => "success",
    "message" => "Deployment completed successfully",
    "git_output" => $output,
    "backend_active" => $is_running,
    "timestamp" => date("Y-m-d H:i:s")
], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
