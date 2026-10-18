' Starts the Tailor-feed static server hidden (used from the Startup folder).
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
port = 8095
If WScript.Arguments.Count > 0 Then port = CLng(WScript.Arguments(0))
CreateObject("WScript.Shell").Run """" & root & "\.venv\Scripts\pythonw.exe"" """ & root & "\serve.py"" --port " & port, 0, False
