' Roda o start_jarvis.bat sem janela de console (usado pela tarefa agendada).
Set shell = CreateObject("WScript.Shell")
shell.Run """" & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\start_jarvis.bat""", 0, False
