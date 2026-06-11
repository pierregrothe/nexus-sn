# CS9240769 -- Réponse à Luc Lalancette (RONA)

Source : schéma réel de l'instance `alectri`, rétro-documenté le 2026-06-08.
Images jointes (PNG, prêtes à coller dans un courriel ou un document) :
`doc-designer-alectri.png` (Document Designer, champ par champ),
`cmdb-bcm-alectri.png` (pont CMDB <-> BCM) et `bcm-alectri.png` (carte BCM/BCP
complète). Versions SVG (vectorielles, pour zoomer sans perte) et Markdown
(source Mermaid, éditable) aussi disponibles.

---

Bonjour Luc,

Excellentes questions -- et tu as raison de vouloir comprendre le pourquoi
plutôt que de copier à l'aveugle. J'ai rétro-documenté directement le modèle de
données sur mon instance de démonstration (les produits installés), donc ce qui
suit est fondé sur les vraies tables, pas sur la doc. Je réponds à tes deux
courriels : (1) la relation Fields / Data Relationships / Content Configuration,
et (2) la carte des tables.

## 1. Relation entre Fields, Data Relationships et Content Configuration

Ton intuition est bonne sur les deux points. Voici ce que confirme le modèle de
données réel.

### Fields -- indépendant (tu avais raison)

Les **Fields** d'un template sont la liste de champs directs portée par la
configuration de modèle elle-même (`sn_grc_doc_design_template_config`, colonne
`fields`, rattachée à la table de base `table`). Ce sont les colonnes du *record
principal* sur lequel le document est généré.

Ils ne dépendent NI d'une Data Relationship NI d'une Content Configuration : tu
peux produire un document composé uniquement de Fields directs. C'est le cas
d'usage le plus simple (un document « plat » sur un seul enregistrement).

### Data Relationship et Content Configuration -- liés (tu avais raison aussi)

C'est la paire à utiliser quand tu veux inclure des données *reliées* (des
enregistrements enfants ou d'une autre table), pas seulement les champs du record
principal.

- **Data Relationship** (`sn_grc_doc_design_data_relationship`) définit COMMENT
  aller d'une table à une autre : `source_table`, `target_table`, `root_table`,
  une relation parente (`parent_relationship`), et surtout elle s'appuie sur le
  Data Registry (`data_registry -> sn_data_registry_relationship`). Elle ne
  référence ni le template ni la content config : c'est une définition
  *réutilisable* d'un « chemin entre deux tables ».

- **Content Configuration** (`sn_grc_doc_design_data_rel_mapping`) est ce qui
  RELIE une Data Relationship à un template précis. Elle référence à la fois
  `template_configuration` ET `data_relationship`, puis précise quoi extraire :
  table cible, condition, regroupement (`group_by`), type d'agrégation, et limite
  du nombre d'enregistrements. C'est exactement la relation que tu avais repérée :
  la Content Configuration pointe vers une entrée de Data Relationship.

- Les colonnes affichées pour ces données reliées sont les **Data Columns**
  (`sn_grc_doc_design_data_column`), rattachées à une Content Configuration
  (`data_relationship_mapping`). À ne pas confondre avec les Fields du template :
  les Fields = champs directs du record principal ; les Data Columns = colonnes
  des données reliées ramenées par une Content Configuration.

### Le pourquoi, en une image

```
Template (sn_grc_doc_design_template_config)
  |
  |-- Fields (colonne `fields`)            -> champs directs du record principal   [INDÉPENDANT]
  |
  |-- Content Configuration (data_rel_mapping)   -> données RELIÉES à inclure
        |-- référence --> Data Relationship (data_relationship)  [le « chemin » réutilisable, via Data Registry]
        |-- Data Columns (data_column)            -> quelles colonnes des données reliées afficher
```

En résumé :
- **Fields** = « quels champs du record principal » -- autonome, utilisable seul.
- **Data Relationship** = « comment rejoindre une table reliée » -- définition
  réutilisable, indépendante du template.
- **Content Configuration** = « dans CE template, ramène les données reliées via
  CETTE Data Relationship, avec ces filtres/regroupements » -- elle dépend de la
  Data Relationship.

Donc tu peux : utiliser des Fields seuls ; réutiliser une même Data Relationship
dans plusieurs Content Configurations ; et modifier/retirer une Content
Configuration sans toucher la Data Relationship sous-jacente.

## 2. Carte des tables -- un ERD plutôt qu'un mind map, et la méthode

Tu demandais un « mind map » des tables ; j'ai produit un **ERD** (diagramme
entité-relation) à la place, parce qu'il répond plus précisément à ta première
question. Chaque table y apparaît avec ses champs clés (clé primaire, colonnes
métier, clés étrangères) et, surtout, les liens entre tables sont tracés
explicitement avec leur cardinalité : on VOIT que la Content Configuration pointe
vers la Data Relationship, au lieu d'avoir à le déduire.

La méthode est reproductible -- c'est exactement ce que j'ai fait : j'ai
rétro-documenté le dictionnaire de données de l'instance (les tables système
`sys_db_object`, `sys_dictionary`, `sys_relationship`) par API, regroupé par
portée applicative, puis rendu en Mermaid. C'est rejouable pour n'importe quel
domaine ; si tu veux d'autres domaines (ou une mise à jour quand tu testes dans
ton PDI), je peux les régénérer.

Tu trouveras en pièce jointe (PNG, plus SVG vectoriel) :

**Document Designer** (`doc-designer-alectri`) -- les 14 tables, sur deux portées
applicatives :
- `sn_grc_doc_design` : la conception du document (Template configuration, Content
  configuration, Data relationship, Data column, Intermediate filter, Scripted
  variable). C'est ici que se lit directement la réponse à ta question 1.
- `sn_grc_rel_config` : la configuration de la carte de relations (noeuds,
  connecteurs, statuts, Nexus map). C'est probablement là que se trouvent des
  tables que tu n'avais pas encore identifiées.

**Pont CMDB <-> BCM** (`cmdb-bcm-alectri`) -- la carte BCM/BCP réduite à son
voisinage de raccord au CMDB. Un seul lien direct vers le CMDB est tracé dans le
diagramme :
- `sn_bcp_recovery_task.configuration_item -> cmdb_ci` (une tâche de reprise
  pointe sur un CI).

Par ailleurs, `sn_bcp_plan_asset` porte un couple `item` / `item_table` (les deux
champs sont visibles dans sa boîte) : c'est le motif de référence polymorphe
ServiceNow (« enregistrement + table cible »). Comme la cible est choisie à
l'exécution via `item_table`, aucune arête fixe n'apparaît dans l'ERD, mais ce
couple peut pointer vers un CI -- la table cible étant alors une classe du CMDB.

**Carte BCM complète** (`bcm-alectri`) -- les 36 tables du domaine BCM/BCP, pour
le détail au-delà du raccord CMDB. C'est là qu'on voit la définition d'élément
(`sn_bcm_element_definition`) et sa colonne `source_table`, qui désigne les
classes CMDB évaluées : c'est le maillon « modèle BCM -> classes CMDB ».

Les fichiers Markdown joints contiennent les diagrammes Mermaid sources si jamais
tu veux les éditer ou les régénérer.

## Prochaines étapes

Pour ton travail dans le PDI la semaine prochaine : commence un document avec
seulement des Fields pour valider le cas autonome, puis ajoute une Content
Configuration pointant sur une Data Relationship OOB pour voir arriver les données
reliées -- tu verras concrètement la dépendance.

Je te propose un court appel pour parcourir les diagrammes et valider que ça
couvre ton besoin. Dis-moi tes disponibilités.

Au plaisir,
Pierre
