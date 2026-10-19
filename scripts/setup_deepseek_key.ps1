param([switch]$Console)
$ErrorActionPreference = 'Stop'
$credentialDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'tmp/deepseek-web'
[void](New-Item -ItemType Directory -Path $credentialDir -Force)
$credentialPath = Join-Path $credentialDir 'api-key.dpapi'
$statusPath = Join-Path $credentialDir 'key-setup-status.json'

function Save-DeepSeekKey([Security.SecureString]$Secret) {
    $encrypted = ConvertFrom-SecureString -SecureString $Secret
    [IO.File]::WriteAllText($credentialPath, $encrypted, [Text.Encoding]::ASCII)
    [IO.File]::WriteAllText($statusPath, '{"key_saved":true,"storage":"Windows DPAPI current user"}')
}

if ($Console) {
    $secret = Read-Host 'DeepSeek API Key (hidden input)' -AsSecureString
    if ($secret.Length -eq 0) { throw 'API Key cannot be empty.' }
    Save-DeepSeekKey $secret
    $secret.Dispose()
    Write-Output 'DeepSeek key saved with Windows DPAPI. No plaintext key was written.'
    exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = 'DeepSeek 搜尋服務 — 本機金鑰設定'
$form.Size = New-Object System.Drawing.Size(570, 245)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.Size = New-Object System.Drawing.Size(520, 60)
$label.Text = "請輸入 DeepSeek API Key（輸入內容會遮蔽）。`n金鑰以 Windows DPAPI 加密，只供目前 Windows 帳號使用。`n不會傳入聊天、日誌或 Git；僅在搜尋／抓取時送往 api.deepseek.com。"
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.Location = New-Object System.Drawing.Point(20, 90)
$inputBox.Size = New-Object System.Drawing.Size(515, 25)
$inputBox.UseSystemPasswordChar = $true
$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Location = New-Object System.Drawing.Point(330, 145)
$saveButton.Size = New-Object System.Drawing.Size(100, 30)
$saveButton.Text = '加密儲存'
$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Location = New-Object System.Drawing.Point(440, 145)
$cancelButton.Size = New-Object System.Drawing.Size(95, 30)
$cancelButton.Text = '取消'
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancelButton
$form.AcceptButton = $saveButton
$saveButton.Add_Click({
    if ([string]::IsNullOrWhiteSpace($inputBox.Text)) { return }
    try {
        $secret = ConvertTo-SecureString $inputBox.Text.Trim() -AsPlainText -Force
        Save-DeepSeekKey $secret
        $inputBox.Clear()
        $secret.Dispose()
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    } catch {
        [void][System.Windows.Forms.MessageBox]::Show('儲存失敗，請確認目錄可寫後重試。')
    }
})
$form.Controls.AddRange(@($label, $inputBox, $saveButton, $cancelButton))
[void]$form.ShowDialog()
$inputBox.Clear()
$form.Dispose()
