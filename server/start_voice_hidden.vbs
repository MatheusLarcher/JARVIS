' Roda o start_voice.bat sem janela de console.
' Existe porque subir o .bat com `cmd /c` deixava a janela aparecer: o
' `windowsHide` do Node esconde o cmd, mas o `timeout.exe` de dentro do loop
' abre console proprio e pisca na tela.
Set shell = CreateObject("WScript.Shell")
shell.Run """" & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\start_voice.bat""", 0, False
