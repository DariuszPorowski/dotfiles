Get-CimInstance -ClassName Win32_Service -Filter 'Name=''ssh-agent''' -Property StartMode,State -OperationTimeoutSec 5 -ErrorAction Stop |
    ForEach-Object { '{0}/{1}' -f $_.StartMode, $_.State }
