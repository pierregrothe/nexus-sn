# Schema ERD: doc-designer

Instance: `alectri`  |  scopes: sn_grc_doc_design, sn_grc_rel_config
Discovered: 2026-06-08T16:20:11.395757+00:00

```mermaid
erDiagram
    sn_grc_doc_design_data_relationship {
        field sys_id PK
        field source_table
        field name
        field root_table
        field target_table
        reference business_domain FK
        reference parent_relationship FK
        reference data_registry FK
    }
    sn_grc_rel_config_edge_status_config {
        field sys_id PK
        field color
        field edge_type
        field label
        field conditions
        field order
        reference edge_config FK
    }
    sn_grc_rel_config_node_status_config {
        field sys_id PK
        field color
        field order
        field conditions
        reference icon FK
        reference node_config FK
    }
    sn_grc_rel_config_main_node_config {
        field sys_id PK
        field table
        field name
        field source
        field max_nodes
        field max_levels
        field conditions
        field active
    }
    sn_grc_doc_design_intermediate_filter {
        field sys_id PK
        field condition
        field active
        field number_of_records
        field name
        field set_record_limit
        reference data_relationship_node FK
        reference content_configuration FK
    }
    sn_grc_doc_design_scripted_variable {
        field sys_id PK
        field type
        field script
        field name
        reference template_configuration FK
    }
    sn_grc_rel_config_node_config {
        field sys_id PK
        field tooltip
        field secondary_label
        field context_record
        field primary_label
        field table
        reference icon FK
        reference set_as_main_node_ui_config FK
        reference data_nav_config FK
    }
    sn_grc_rel_config_graph_element_base {
        field sys_id PK
        field field_mapping
        field active
        reference main_node_ui_config FK
    }
    sn_grc_doc_design_data_rel_mapping {
        field sys_id PK
        field aggregation_type
        field name
        field number_of_records
        field target_table
        field group_by
        field aggregation_query
        field condition
        field aggregation_field
        reference parent_relationship_mapping FK
        reference data_relationship FK
        reference template_configuration FK
    }
    sn_grc_rel_config_main_node_ui_config {
        field sys_id PK
        field name
        field workspace_type
        field short_description
        field active
        field node_ui_type
        reference main_node_config FK
    }
    sn_grc_doc_design_template_config {
        field sys_id PK
        field fields
        field name
        field table
        reference business_domain FK
    }
    sn_grc_rel_config_edge_config {
        field sys_id PK
        field tooltip
        field default_edge_type
        field label
        reference node_relationship_config FK
    }
    sn_grc_doc_design_data_column {
        field sys_id PK
        field script
        field column_name
        field column
        field type
        reference data_relationship_mapping FK
    }
    sn_grc_rel_config_node_rel_config {
        field sys_id PK
        field max_children
        field sort_by
        field type
        field max_levels
        field direction
        field order
        field query_category
        field name
        field target_conditions
        field active
        field relationship_table
        field target_ref_field
        field source_table
        field relationship_conditions
        field target_table
        field sequence
        reference rel_registry FK
        reference main_node_config FK
    }
    sn_grc_rel_config_main_node_ui_config }o--|| sn_grc_rel_config_main_node_config : "main_node_config"
    sn_grc_doc_design_data_relationship }o--|| sn_esg_msoff_intg_business_domain : "business_domain"
    sn_grc_doc_design_data_rel_mapping }o--|| sn_grc_doc_design_data_rel_mapping : "parent_relationship_mapping"
    sn_grc_doc_design_data_column }o--|| sn_grc_doc_design_data_rel_mapping : "data_relationship_mapping"
    sn_grc_rel_config_node_status_config }o--|| st_sys_design_system_icon : "icon"
    sn_grc_doc_design_data_relationship }o--|| sn_grc_doc_design_data_relationship : "parent_relationship"
    sn_grc_doc_design_intermediate_filter }o--|| sn_grc_doc_design_data_relationship : "data_relationship_node"
    sn_grc_doc_design_scripted_variable }o--|| sn_grc_doc_design_template_config : "template_configuration"
    sn_grc_rel_config_node_rel_config }o--|| sn_data_registry_relationship : "rel_registry"
    sn_grc_rel_config_node_config }o--|| st_sys_design_system_icon : "icon"
    sn_grc_rel_config_node_status_config }o--|| sn_grc_rel_config_node_config : "node_config"
    sn_grc_rel_config_edge_status_config }o--|| sn_grc_rel_config_edge_config : "edge_config"
    sn_grc_doc_design_data_rel_mapping }o--|| sn_grc_doc_design_data_relationship : "data_relationship"
    sn_grc_rel_config_node_config }o--|| sn_grc_rel_config_main_node_ui_config : "set_as_main_node_ui_config"
    sn_grc_doc_design_template_config }o--|| sn_esg_msoff_intg_business_domain : "business_domain"
    sn_grc_rel_config_node_rel_config }o--|| sn_grc_rel_config_main_node_config : "main_node_config"
    sn_grc_rel_config_edge_config }o--|| sn_grc_rel_config_node_rel_config : "node_relationship_config"
    sn_grc_doc_design_intermediate_filter }o--|| sn_grc_doc_design_data_rel_mapping : "content_configuration"
    sn_grc_doc_design_data_relationship }o--|| sn_data_registry_relationship : "data_registry"
    sn_grc_rel_config_graph_element_base }o--|| sn_grc_rel_config_main_node_ui_config : "main_node_ui_config"
    sn_grc_doc_design_data_rel_mapping }o--|| sn_grc_doc_design_template_config : "template_configuration"
    sn_grc_rel_config_node_config }o--|| sn_data_navigator_config : "data_nav_config"
    sys_metadata ||--|| sn_grc_rel_config_edge_status_config : "extends"
    sys_metadata ||--|| sn_grc_rel_config_node_status_config : "extends"
    sys_metadata ||--|| sn_grc_rel_config_main_node_config : "extends"
    sn_grc_rel_config_graph_element_base ||--|| sn_grc_rel_config_node_config : "extends"
    sys_metadata ||--|| sn_grc_rel_config_graph_element_base : "extends"
    sys_metadata ||--|| sn_grc_rel_config_main_node_ui_config : "extends"
    sn_grc_rel_config_graph_element_base ||--|| sn_grc_rel_config_edge_config : "extends"
    sys_metadata ||--|| sn_grc_rel_config_node_rel_config : "extends"
```

## Cross-scope bridges

- sn_grc_doc_design_data_relationship.business_domain -> sn_esg_msoff_intg_business_domain
- sn_grc_rel_config_node_status_config.icon -> st_sys_design_system_icon
- sn_grc_rel_config_node_rel_config.rel_registry -> sn_data_registry_relationship
- sn_grc_rel_config_node_config.icon -> st_sys_design_system_icon
- sn_grc_doc_design_template_config.business_domain -> sn_esg_msoff_intg_business_domain
- sn_grc_doc_design_data_relationship.data_registry -> sn_data_registry_relationship
- sn_grc_rel_config_node_config.data_nav_config -> sn_data_navigator_config

## Fields

### sn_grc_doc_design_data_relationship -- Data relationship

| Field | Type | References |
| --- | --- | --- |
| sys_mod_count | field |  |
| source_table | field |  |
| sys_domain | field |  |
| sys_domain_path | field |  |
| business_domain | reference | sn_esg_msoff_intg_business_domain |
| sys_updated_by | field |  |
| sys_updated_on | field |  |
| parent_relationship | reference | sn_grc_doc_design_data_relationship |
| name | field |  |
| root_table | field |  |
| sys_created_by | field |  |
| data_registry | reference | sn_data_registry_relationship |
| sys_id | field |  |
| sys_created_on | field |  |
| target_table | field |  |

### sn_grc_rel_config_edge_status_config -- Connector status configuration

| Field | Type | References |
| --- | --- | --- |
| color | field |  |
| sys_domain | field |  |
| sys_id | field |  |
| edge_type | field |  |
| label | field |  |
| edge_config | reference | sn_grc_rel_config_edge_config |
| conditions | field |  |
| order | field |  |
| sys_domain_path | field |  |

### sn_grc_rel_config_node_status_config -- Node status configuration

| Field | Type | References |
| --- | --- | --- |
| sys_domain | field |  |
| color | field |  |
| icon | reference | st_sys_design_system_icon |
| sys_domain_path | field |  |
| node_config | reference | sn_grc_rel_config_node_config |
| sys_id | field |  |
| order | field |  |
| conditions | field |  |

### sn_grc_rel_config_main_node_config -- Main node configuration

| Field | Type | References |
| --- | --- | --- |
| sys_domain | field |  |
| table | field |  |
| name | field |  |
| source | field |  |
| max_nodes | field |  |
| max_levels | field |  |
| conditions | field |  |
| active | field |  |
| sys_id | field |  |
| sys_domain_path | field |  |

### sn_grc_doc_design_intermediate_filter -- Intermediate filter

| Field | Type | References |
| --- | --- | --- |
| sys_domain | field |  |
| sys_created_by | field |  |
| sys_mod_count | field |  |
| sys_updated_by | field |  |
| condition | field |  |
| active | field |  |
| data_relationship_node | reference | sn_grc_doc_design_data_relationship |
| sys_id | field |  |
| number_of_records | field |  |
| sys_updated_on | field |  |
| sys_domain_path | field |  |
| sys_created_on | field |  |
| content_configuration | reference | sn_grc_doc_design_data_rel_mapping |
| name | field |  |
| set_record_limit | field |  |

### sn_grc_doc_design_scripted_variable -- Scripted variable

| Field | Type | References |
| --- | --- | --- |
| sys_mod_count | field |  |
| type | field |  |
| sys_domain_path | field |  |
| sys_created_by | field |  |
| sys_updated_by | field |  |
| template_configuration | reference | sn_grc_doc_design_template_config |
| script | field |  |
| sys_created_on | field |  |
| sys_domain | field |  |
| name | field |  |
| sys_id | field |  |
| sys_updated_on | field |  |

### sn_grc_rel_config_node_config -- Node configuration

| Field | Type | References |
| --- | --- | --- |
| tooltip | field |  |
| secondary_label | field |  |
| context_record | field |  |
| primary_label | field |  |
| icon | reference | st_sys_design_system_icon |
| table | field |  |
| set_as_main_node_ui_config | reference | sn_grc_rel_config_main_node_ui_config |
| sys_id | field |  |
| data_nav_config | reference | sn_data_navigator_config |

### sn_grc_rel_config_graph_element_base -- Graph element base configuration

| Field | Type | References |
| --- | --- | --- |
| sys_domain_path | field |  |
| sys_domain | field |  |
| sys_id | field |  |
| field_mapping | field |  |
| active | field |  |
| main_node_ui_config | reference | sn_grc_rel_config_main_node_ui_config |

### sn_grc_doc_design_data_rel_mapping -- Content configuration

| Field | Type | References |
| --- | --- | --- |
| parent_relationship_mapping | reference | sn_grc_doc_design_data_rel_mapping |
| sys_domain | field |  |
| aggregation_type | field |  |
| name | field |  |
| number_of_records | field |  |
| sys_created_by | field |  |
| sys_mod_count | field |  |
| target_table | field |  |
| group_by | field |  |
| sys_updated_by | field |  |
| sys_domain_path | field |  |
| aggregation_query | field |  |
| data_relationship | reference | sn_grc_doc_design_data_relationship |
| condition | field |  |
| sys_id | field |  |
| template_configuration | reference | sn_grc_doc_design_template_config |
| sys_updated_on | field |  |
| aggregation_field | field |  |
| sys_created_on | field |  |

### sn_grc_rel_config_main_node_ui_config -- Nexus map configuration

| Field | Type | References |
| --- | --- | --- |
| sys_domain | field |  |
| name | field |  |
| main_node_config | reference | sn_grc_rel_config_main_node_config |
| workspace_type | field |  |
| sys_domain_path | field |  |
| short_description | field |  |
| sys_id | field |  |
| active | field |  |
| node_ui_type | field |  |

### sn_grc_doc_design_template_config -- Template configuration

| Field | Type | References |
| --- | --- | --- |
| sys_domain | field |  |
| sys_updated_on | field |  |
| sys_domain_path | field |  |
| sys_created_on | field |  |
| fields | field |  |
| sys_id | field |  |
| business_domain | reference | sn_esg_msoff_intg_business_domain |
| name | field |  |
| sys_updated_by | field |  |
| table | field |  |
| sys_created_by | field |  |
| sys_mod_count | field |  |

### sn_grc_rel_config_edge_config -- Connector configuration

| Field | Type | References |
| --- | --- | --- |
| tooltip | field |  |
| default_edge_type | field |  |
| label | field |  |
| node_relationship_config | reference | sn_grc_rel_config_node_rel_config |
| sys_id | field |  |

### sn_grc_doc_design_data_column -- Data column

| Field | Type | References |
| --- | --- | --- |
| script | field |  |
| sys_created_on | field |  |
| data_relationship_mapping | reference | sn_grc_doc_design_data_rel_mapping |
| sys_domain | field |  |
| sys_updated_by | field |  |
| sys_domain_path | field |  |
| column_name | field |  |
| sys_updated_on | field |  |
| column | field |  |
| sys_created_by | field |  |
| type | field |  |
| sys_id | field |  |
| sys_mod_count | field |  |

### sn_grc_rel_config_node_rel_config -- Node relationship configuration

| Field | Type | References |
| --- | --- | --- |
| max_children | field |  |
| sort_by | field |  |
| type | field |  |
| sys_domain_path | field |  |
| sys_id | field |  |
| max_levels | field |  |
| direction | field |  |
| order | field |  |
| rel_registry | reference | sn_data_registry_relationship |
| sys_domain | field |  |
| query_category | field |  |
| name | field |  |
| main_node_config | reference | sn_grc_rel_config_main_node_config |
| target_conditions | field |  |
| active | field |  |
| relationship_table | field |  |
| target_ref_field | field |  |
| source_table | field |  |
| relationship_conditions | field |  |
| target_table | field |  |
| sequence | field |  |
