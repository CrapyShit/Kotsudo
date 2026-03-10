param(
    [Parameter(Mandatory=$true, Position=0)] [string] $Script,
    [string] $MayaHost = "127.0.0.1",
    [int] $MayaPort = 7002,
    [int] $TimeoutMs = 3000
)

function Write-Err($msg) { Write-Host "[send_to_maya.ps1] $msg" -ForegroundColor Red }
function Write-Ok($msg) { Write-Host "[send_to_maya.ps1] $msg" -ForegroundColor Green }

try {
    $full = [System.IO.Path]::GetFullPath($Script)
    if (-not (Test-Path -Path $full -PathType Leaf)) {
        Write-Err "File not found: $Script"
        exit 2
    }

    # Escape for embedding inside a Python raw string literal r'...'
    $p = $full -replace "\\", "\\\\" -replace "'", "\\'"
    $code = "import runpy, sys; p=r'$p'; sys.__dict__.setdefault('__file__', p); runpy.run_path(p, run_name='__main__')`n"

    $client = New-Object System.Net.Sockets.TcpClient
    $client.SendTimeout = $TimeoutMs
    $client.ReceiveTimeout = $TimeoutMs

    try {
    $client.Connect($MayaHost, $MayaPort)
    }
    catch {
    Write-Err "Could not connect to Maya commandPort at ${MayaHost}:${MayaPort} — $($_.Exception.Message)"
        $client.Close()
        exit 3
    }

    try {
        $stream = $client.GetStream()
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($code)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        $stream.Dispose()
        $client.Close()
    Write-Ok "Sent $full to Maya at ${MayaHost}:${MayaPort}"
        exit 0
    }
    catch {
        Write-Err "Failed to send to Maya — $($_.Exception.Message)"
        try { $client.Close() } catch {}
        exit 4
    }
}
catch {
    Write-Err "Unexpected error — $($_.Exception.Message)"
    exit 1
}
