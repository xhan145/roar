# WiX Directory Structure Analysis

## Key Facts from Code:
1. installer/flowlocal.wxs line 11-14:
   - LocalAppDataFolder (standard predefined)
     - ProgramsFolder (also declared as Id="ProgramsFolder", Name="Programs")
       - INSTALLDIR (custom, Name="FlowLocal")

2. InstallScope="perUser" (line 6) - this is a per-user installation

3. The build SUCCEEDED:
   - heat.exe completed successfully and generated harvest.wxs
   - candle.exe compiled both .wxs files to .wixobj without errors
   - light.exe linked them to create dist/FlowLocal-0.2.0.msi (747MB file exists)

4. The harvest.wxs references DirectoryRef Id="INSTALLDIR" successfully

## Critical Question:
Is "ProgramsFolder" treated as:
A) A WiX predefined constant (special) that cannot be nested under LocalAppDataFolder?
B) Just a regular Directory element with Id="ProgramsFolder" and Name="Programs"?

## Analysis:
The finding claims: "ProgramsFolder is a standard WiX predefined directory that maps to 
Program Files, not a subfolder within %LOCALAPPDATA%. ... This will cause the heat.exe 
tool to fail during MSI generation or create an invalid/unreachable install location."

However: The build DID complete successfully with no errors from heat.exe, candle.exe, or 
light.exe. The MSI file exists and is ~750MB in size, suggesting the linking succeeded.

## WiX Semantics:
In WiX, when you write:
```
<Directory Id="LocalAppDataFolder">
  <Directory Id="ProgramsFolder" Name="Programs">
```

This creates a NESTED directory structure where ProgramsFolder is just a logical directory ID
with the NAME "Programs" - it does NOT automatically resolve to the special predefined 
ProgramsFolder constant (which would map to Program Files).

The Id="ProgramsFolder" is just a user-assigned identifier for reference within the WiX source.
The Name="Programs" is what gets created on disk as a subfolder.

So the actual install path would be: %LOCALAPPDATA%\Programs\FlowLocal

This is NOT an error - it's a valid per-user installation pattern.
