Attribute VB_Name = "FormatRiskReport"
' Import into risk_report.xlsx: Alt+F11 > File > Import File, then save as .xlsm.
' Run FormatReport after each new Python run.

Option Explicit

Sub FormatReport()
    Dim ws As Worksheet
    For Each ws In ThisWorkbook.Worksheets
        With ws.Rows(1)
            .Font.Bold = True
            .Interior.Color = RGB(31, 78, 121)
            .Font.Color = vbWhite
        End With
        ws.Columns.AutoFit
        ws.Activate
        ActiveWindow.FreezePanes = False
        ws.Range("A2").Select
        ActiveWindow.FreezePanes = True
    Next ws
    HighlightLimits
    ThisWorkbook.Worksheets("Summary").Activate
End Sub

Sub HighlightLimits()
    ' Colours the Status column and pops up a message listing any breached desks.
    Dim ws As Worksheet, r As Long, lastRow As Long, statusCol As Long
    Dim breached As String

    Set ws = ThisWorkbook.Worksheets("Limits")
    statusCol = Application.Match("Status", ws.Rows(1), 0)
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    For r = 2 To lastRow
        Select Case ws.Cells(r, statusCol).Value
            Case "BREACH"
                ws.Cells(r, statusCol).Interior.Color = RGB(248, 203, 173)
                breached = breached & vbCrLf & " - " & ws.Cells(r, 1).Value
            Case "WARNING"
                ws.Cells(r, statusCol).Interior.Color = RGB(255, 230, 153)
            Case Else
                ws.Cells(r, statusCol).Interior.Color = RGB(198, 224, 180)
        End Select
    Next r

    If Len(breached) > 0 Then
        MsgBox "VaR limit breached for:" & breached, vbExclamation, "Limit monitoring"
    Else
        MsgBox "All desks within limits.", vbInformation, "Limit monitoring"
    End If
End Sub
