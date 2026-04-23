# App Commands And Shortcuts Plan

Date: 2026-04-23

Cette doc decrit la cible globale pour les commandes et raccourcis clavier de l'application. Le systeme ne doit pas etre specifique au board: le board est seulement un domaine parmi d'autres.

## Principe

Un raccourci clavier ne doit jamais appeler directement une methode de controller.

Le flux cible est:

```text
keyboard shortcut
  -> command id
  -> global command dispatcher
  -> domain dispatcher
  -> action metier
```

Exemple:

```text
L
  -> board.layout.auto
  -> board dispatcher
  -> BoardAction(kind="layout_selection_grid")
```

Demain, le meme systeme doit pouvoir gerer:

- projets
- asset manager
- client sync
- settings
- dev tools
- board
- tools du board

## Concepts

### AppCommand

Une commande decrit une intention utilisateur.

Exemples:

```text
board.layout.auto
board.view.fit
board.focus.exit
project.open_selected
asset.copy_path
client.sync.preview
app.command_palette.open
```

Une commande porte:

- un id stable
- un label humain
- un domaine
- un scope
- des raccourcis par defaut
- une description optionnelle

### Domain

Le domaine sert au dispatch:

```text
app
projects
asset_manager
board
client
settings
dev
```

Le dispatcher global ne connait pas la logique metier. Il route vers le dispatcher du domaine.

### Scope

Le scope sert a savoir quand un raccourci est actif.

Scopes cibles:

```text
global
projects
asset_manager
board
board.focus
board.edit
board.timeline
board.tool
client
settings
dev
```

Les champs texte restent un cas special: quand un champ texte edite du texte, les raccourcis comme `L` ne doivent pas etre interceptes.

### ShortcutBinding

Un binding relie une sequence clavier a une commande:

```text
scope=board
sequence=L
command_id=board.layout.auto
source=default
```

Les bindings effectifs viennent de:

- raccourcis par defaut declares par les commandes
- overrides utilisateur dans les settings

Les settings ne doivent stocker que les overrides:

```json
{
  "shortcuts": {
    "board.layout.auto": ["L"],
    "board.view.fit": ["F"]
  }
}
```

Une liste vide desactive les raccourcis d'une commande.

## Conflits

Le systeme doit detecter les conflits avant que l'utilisateur les decouvre par hasard.

Deux bindings sont en conflit si:

- ils utilisent la meme sequence normalisee
- leurs scopes se chevauchent
- ils pointent vers deux commandes differentes

Exemples:

- `global: Ctrl+K` entre en conflit avec `board: Ctrl+K`
- `board: L` entre en conflit avec `board.edit: L`
- `board: L` ne conflit pas avec `projects: L`

## Structure Cible

```text
core/
  commands/
    command.py       # AppCommand, CommandContext, CommandResult
    registry.py      # CommandRegistry, validation commands
    scopes.py        # scopes connus et chevauchements
    shortcuts.py     # ShortcutBinding, overrides, conflits

controllers/
  app_command_controller.py
  app_shortcuts_controller.py
  board_command_dispatcher.py
```

Le core doit rester pur et testable, sans Qt.

## Plan D'Implementation

### Phase 1. Core Pur

- creer `AppCommand`
- creer `CommandRegistry`
- creer `ShortcutBinding`
- creer la resolution defaults + overrides
- creer la detection de conflits
- tester tout ca sans Qt

### Phase 2. Commandes Initiales

Ajouter les commandes de base:

- `board.layout.auto` -> default `L`
- `board.view.fit` -> default `F`
- `board.view.toggle_grid` -> default `G`
- `board.focus.exit` -> default `Escape`
- `app.command_palette.open` -> default `Ctrl+K`

Statut: base ajoutee dans `core/commands/defaults.py`.

### Phase 3. Dispatchers

- creer un dispatcher global
- creer un dispatcher board
- brancher les commandes board vers les actions existantes
- a terme, faire produire des `BoardAction`

Statut: dispatchers initiaux ajoutes dans `controllers/app_command_controller.py` et `controllers/board_command_dispatcher.py`.

### Phase 4. Qt Shortcuts

- installer les raccourcis au niveau fenetre principale
- resoudre le scope actif
- ignorer les raccourcis dangereux pendant edition texte
- appeler le dispatcher global

Statut: branche initiale ajoutee dans `controllers/app_shortcuts_controller.py`. Le controller installe des `QShortcut` au niveau fenetre pour les domaines qui ont deja un dispatcher, resout le scope actif depuis la page courante, bascule `board` vers `board.focus` quand un item est en focus, ignore les raccourcis non globaux pendant l'edition texte, puis appelle `AppCommandController`.

### Phase 5. Settings

- lire `"shortcuts"` depuis les settings
- sauvegarder les overrides
- detecter les conflits utilisateur
- plus tard: UI de configuration

Statut: les overrides sont lus depuis `settings["shortcuts"]`, normalises par `core.settings`, et reappliques quand les settings sont sauvegardes depuis l'UI. Les conflits sont detectes avant installation; les sequences conflictuelles sont ignorees pour eviter un comportement ambigu.

Une premiere UI existe dans `Settings > Shortcuts`. Elle liste les commandes declarees, affiche les raccourcis effectifs, accepte plusieurs sequences separees par virgule, et sauvegarde seulement les valeurs differentes des defaults. Un champ vide sauvegarde une liste vide et desactive les raccourcis de la commande.

### Phase 6. Commands De Tools

- permettre aux tools de declarer leurs commandes
- namespace: `board.tool.<tool_id>.<command>`
- dispatcher via tool actif ou tool specifique

## Regles Anti-Dette

- pas de `if key == ...` disperse dans les widgets
- pas de noms de methodes Python dans les settings
- pas de logique Qt dans `core.commands`
- pas de dispatcher global qui connait la logique metier des domaines
- pas de raccourci board-only deguise en systeme global

La premiere brique doit rester modeste: le modele pur et ses tests.
