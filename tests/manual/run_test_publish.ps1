$hython = "C:\Program Files\Side Effects Software\Houdini 21.0.559\bin\hython.exe"
$request = Join-Path $PSScriptRoot "test_publish_request.json"

& $hython -m houdini_pipeline.process_runner --request-file $request
