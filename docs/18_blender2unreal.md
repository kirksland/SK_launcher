Structure propre : **séparer le core du plugin Blender**.

Le plugin Blender ne doit pas être “le cerveau”. Il doit juste être une interface.

Architecture :

```txt
skyforge_bridge/
    core/
        asset_model.py
        export_plan.py
        validation.py
        path_resolver.py
        manifest.py
        logging.py

    blender/
        ui_panel.py
        operators.py
        scene_reader.py
        blender_exporter.py
        presets.py

    unreal/
        unreal_importer.py
        unreal_commands.py
        material_builder.py
        reimport_manager.py

    formats/
        fbx_export.py
        gltf_export.py
        usd_export.py

    data/
        project_config.json
        export_presets.json
        asset_manifest.json
```

L’idée :

Blender lit la scène → crée une description neutre de l’asset → le core génère un plan d’export → Blender exporte → Unreal importe → un manifest garde la trace.

Exemple de flow :

```txt
Blender object selected
        ↓
SceneReader
        ↓
AssetDescriptor
        ↓
Validator
        ↓
ExportPlan
        ↓
Exporter FBX/USD/glTF
        ↓
Manifest update
        ↓
Unreal Importer
        ↓
Reimport / create asset
```

Le point important : **AssetDescriptor**.

Un asset devrait être décrit comme ça, peu importe qu’il vienne de Blender, Houdini ou autre :

```python
AssetDescriptor:
    name
    source_file
    source_object
    asset_type  # static_mesh, skeletal_mesh, animation, groom...
    export_path
    unreal_path
    materials
    textures
    lods
    collisions
    metadata
```

Comme ça, plus tard Skyforge peut générer les mêmes descriptors depuis ton app, Houdini, un dossier, un batch, etc.

Le deuxième point important : **manifest**.

Un fichier qui garde la mémoire :

```json
{
  "asset_id": "chair_wood_01",
  "source": "C:/project/blender/chair.blend",
  "object": "SM_Chair",
  "export_file": "C:/project/exports/chair.fbx",
  "unreal_path": "/Game/Props/Chair",
  "last_export_hash": "...",
  "material_policy": "preserve_unreal",
  "created_at": "...",
  "updated_at": "..."
}
```

C’est lui qui permet l’update propre. Sans manifest, tu fais juste du bricolage avec un bouton export.

Dans Blender, tu aurais seulement :

```txt
Panel Skyforge Unreal Bridge
    Project
    Unreal Target Path
    Preset
    Validate
    Send Selected
    Send Collection
    Update Last Export
```

Les operators Blender appellent le core :

```python
bpy.ops.skyforge.send_selected()
bpy.ops.skyforge.validate_selected()
bpy.ops.skyforge.update_asset()
```

Mais ils ne contiennent presque pas de logique métier.

Côté Unreal, évite de dépendre uniquement d’une UI. Il faut un script Python Unreal qui peut être lancé :

* depuis Unreal ouvert ;
* depuis une commande ;
* depuis Skyforge plus tard.

Genre :

```txt
unreal_importer.py --manifest asset_manifest.json --mode import
```

Pour le format, je ferais :

* **FBX** pour MVP static mesh / skeletal / anim
* **USD** plus tard pour scène/layout/instances
* **glTF** éventuellement pour preview ou trucs web/app

Le MVP propre :

```txt
1. AssetDescriptor
2. Validator
3. FBX exporter Blender
4. Unreal Python importer
5. Manifest
6. UI Blender minimale
```

Pas plus au début. Sinon vous allez construire une cathédrale, et comme d’habitude personne ne saura où est la porte.

Le truc à ne surtout pas faire : coder toute la logique directement dans les boutons Blender.
Sinon quand tu voudras brancher ça dans Skyforge, tu devras tout arracher au pied-de-biche.
