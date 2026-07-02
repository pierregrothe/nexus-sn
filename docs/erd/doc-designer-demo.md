# Schema ERD: doc-designer

Instance: `alectri`  |  scopes: sn_grc_doc_design, sn_grc_rel_config
Discovered: 2026-06-11T16:37:54.156167+00:00

```mermaid
erDiagram
    sn_grc_doc_design_data_column {
        GUID sys_id PK
        field_name column
        translated_text column_name
        script script
        choice type
        reference data_relationship_mapping FK
    }
    sn_grc_doc_design_data_rel_mapping {
        GUID sys_id PK
        field_name aggregation_field
        boolean aggregation_query
        choice aggregation_type
        conditions condition
        field_name group_by
        string name
        integer number_of_records
        table_name target_table
        reference data_relationship FK
        reference parent_relationship_mapping FK
        reference template_configuration FK
    }
    sn_grc_doc_design_data_relationship {
        GUID sys_id PK
        string name
        table_name root_table
        table_name source_table
        table_name target_table
        reference business_domain FK
        reference data_registry FK
        reference parent_relationship FK
    }
    sn_grc_doc_design_intermediate_filter {
        GUID sys_id PK
        boolean active
        conditions condition
        string name
        integer number_of_records
        boolean set_record_limit
        reference content_configuration FK
        reference data_relationship_node FK
    }
    sn_grc_doc_design_scripted_variable {
        GUID sys_id PK
        string name
        script script
        choice type
        reference template_configuration FK
    }
    sn_grc_doc_design_template_config {
        GUID sys_id PK
        field_list fields
        string name
        table_name table
        reference business_domain FK
    }
    sn_grc_rel_config_edge_config {
        GUID sys_id PK
        choice default_edge_type
        field_name label
        field_name tooltip
        reference node_relationship_config FK
    }
    sn_grc_rel_config_edge_status_config {
        GUID sys_id PK
        choice color
        conditions conditions
        choice edge_type
        translated_text label
        integer order
        reference edge_config FK
    }
    sn_grc_rel_config_graph_element_base {
        GUID sys_id PK
        boolean active
        json field_mapping
        reference main_node_ui_config FK
    }
    sn_grc_rel_config_main_node_config {
        GUID sys_id PK
        boolean active
        conditions conditions
        integer max_levels
        integer max_nodes
        string name
        string source
        table_name table
    }
    sn_grc_rel_config_main_node_ui_config {
        GUID sys_id PK
        boolean active
        string name
        choice node_ui_type
        string short_description
        choice workspace_type
        reference main_node_config FK
    }
    sn_grc_rel_config_node_config {
        GUID sys_id PK
        field_name context_record
        field_name primary_label
        field_name secondary_label
        table_name table
        field_name tooltip
        reference data_nav_config FK
        reference icon FK
        reference set_as_main_node_ui_config FK
    }
    sn_grc_rel_config_node_rel_config {
        GUID sys_id PK
        boolean active
        string direction
        integer max_children
        integer max_levels
        string name
        string order
        string query_category
        conditions relationship_conditions
        table_name relationship_table
        integer sequence
        field_name sort_by
        table_name source_table
        conditions target_conditions
        field_name target_ref_field
        table_name target_table
        string type
        reference main_node_config FK
        reference rel_registry FK
    }
    sn_grc_rel_config_node_status_config {
        GUID sys_id PK
        choice color
        conditions conditions
        integer order
        reference icon FK
        reference node_config FK
    }
    sn_grc_doc_design_data_column }o--|| sn_grc_doc_design_data_rel_mapping : "data_relationship_mapping"
    sn_grc_doc_design_data_rel_mapping }o--|| sn_grc_doc_design_data_relationship : "data_relationship"
    sn_grc_doc_design_data_rel_mapping }o--|| sn_grc_doc_design_data_rel_mapping : "parent_relationship_mapping"
    sn_grc_doc_design_data_rel_mapping }o--|| sn_grc_doc_design_template_config : "template_configuration"
    sn_grc_doc_design_data_relationship }o--|| sn_esg_msoff_intg_business_domain : "business_domain"
    sn_grc_doc_design_data_relationship }o--|| sn_data_registry_relationship : "data_registry"
    sn_grc_doc_design_data_relationship }o--|| sn_grc_doc_design_data_relationship : "parent_relationship"
    sn_grc_doc_design_intermediate_filter }o--|| sn_grc_doc_design_data_rel_mapping : "content_configuration"
    sn_grc_doc_design_intermediate_filter }o--|| sn_grc_doc_design_data_relationship : "data_relationship_node"
    sn_grc_doc_design_scripted_variable }o--|| sn_grc_doc_design_template_config : "template_configuration"
    sn_grc_doc_design_template_config }o--|| sn_esg_msoff_intg_business_domain : "business_domain"
    sn_grc_rel_config_edge_config }o--|| sn_grc_rel_config_node_rel_config : "node_relationship_config"
    sn_grc_rel_config_edge_status_config }o--|| sn_grc_rel_config_edge_config : "edge_config"
    sn_grc_rel_config_graph_element_base }o--|| sn_grc_rel_config_main_node_ui_config : "main_node_ui_config"
    sn_grc_rel_config_main_node_ui_config }o--|| sn_grc_rel_config_main_node_config : "main_node_config"
    sn_grc_rel_config_node_config }o--|| sn_data_navigator_config : "data_nav_config"
    sn_grc_rel_config_node_config }o--|| st_sys_design_system_icon : "icon"
    sn_grc_rel_config_node_config }o--|| sn_grc_rel_config_main_node_ui_config : "set_as_main_node_ui_config"
    sn_grc_rel_config_node_rel_config }o--|| sn_grc_rel_config_main_node_config : "main_node_config"
    sn_grc_rel_config_node_rel_config }o--|| sn_data_registry_relationship : "rel_registry"
    sn_grc_rel_config_node_status_config }o--|| st_sys_design_system_icon : "icon"
    sn_grc_rel_config_node_status_config }o--|| sn_grc_rel_config_node_config : "node_config"
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
- sn_grc_doc_design_data_relationship.data_registry -> sn_data_registry_relationship
- sn_grc_doc_design_template_config.business_domain -> sn_esg_msoff_intg_business_domain
- sn_grc_rel_config_node_config.data_nav_config -> sn_data_navigator_config
- sn_grc_rel_config_node_config.icon -> st_sys_design_system_icon
- sn_grc_rel_config_node_rel_config.rel_registry -> sn_data_registry_relationship
- sn_grc_rel_config_node_status_config.icon -> st_sys_design_system_icon

## Fields

### sn_grc_doc_design_data_column -- Data column

| Field | Type | References |
| --- | --- | --- |
| column | field_name |  |
| column_name | translated_text |  |
| data_relationship_mapping | reference | sn_grc_doc_design_data_rel_mapping |
| script | script |  |
| sys_created_by | string |  |
| sys_created_on | glide_date_time |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| sys_mod_count | integer |  |
| sys_updated_by | string |  |
| sys_updated_on | glide_date_time |  |
| type | choice |  |

### sn_grc_doc_design_data_rel_mapping -- Content configuration

| Field | Type | References |
| --- | --- | --- |
| aggregation_field | field_name |  |
| aggregation_query | boolean |  |
| aggregation_type | choice |  |
| condition | conditions |  |
| data_relationship | reference | sn_grc_doc_design_data_relationship |
| group_by | field_name |  |
| name | string |  |
| number_of_records | integer |  |
| parent_relationship_mapping | reference | sn_grc_doc_design_data_rel_mapping |
| sys_created_by | string |  |
| sys_created_on | glide_date_time |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| sys_mod_count | integer |  |
| sys_updated_by | string |  |
| sys_updated_on | glide_date_time |  |
| target_table | table_name |  |
| template_configuration | reference | sn_grc_doc_design_template_config |

### sn_grc_doc_design_data_relationship -- Data relationship

| Field | Type | References |
| --- | --- | --- |
| business_domain | reference | sn_esg_msoff_intg_business_domain |
| data_registry | reference | sn_data_registry_relationship |
| name | string |  |
| parent_relationship | reference | sn_grc_doc_design_data_relationship |
| root_table | table_name |  |
| source_table | table_name |  |
| sys_created_by | string |  |
| sys_created_on | glide_date_time |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| sys_mod_count | integer |  |
| sys_updated_by | string |  |
| sys_updated_on | glide_date_time |  |
| target_table | table_name |  |

### sn_grc_doc_design_intermediate_filter -- Intermediate filter

| Field | Type | References |
| --- | --- | --- |
| active | boolean |  |
| condition | conditions |  |
| content_configuration | reference | sn_grc_doc_design_data_rel_mapping |
| data_relationship_node | reference | sn_grc_doc_design_data_relationship |
| name | string |  |
| number_of_records | integer |  |
| set_record_limit | boolean |  |
| sys_created_by | string |  |
| sys_created_on | glide_date_time |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| sys_mod_count | integer |  |
| sys_updated_by | string |  |
| sys_updated_on | glide_date_time |  |

### sn_grc_doc_design_scripted_variable -- Scripted variable

| Field | Type | References |
| --- | --- | --- |
| name | string |  |
| script | script |  |
| sys_created_by | string |  |
| sys_created_on | glide_date_time |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| sys_mod_count | integer |  |
| sys_updated_by | string |  |
| sys_updated_on | glide_date_time |  |
| template_configuration | reference | sn_grc_doc_design_template_config |
| type | choice |  |

### sn_grc_doc_design_template_config -- Template configuration

| Field | Type | References |
| --- | --- | --- |
| business_domain | reference | sn_esg_msoff_intg_business_domain |
| fields | field_list |  |
| name | string |  |
| sys_created_by | string |  |
| sys_created_on | glide_date_time |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| sys_mod_count | integer |  |
| sys_updated_by | string |  |
| sys_updated_on | glide_date_time |  |
| table | table_name |  |

### sn_grc_rel_config_edge_config -- Connector configuration

| Field | Type | References |
| --- | --- | --- |
| default_edge_type | choice |  |
| label | field_name |  |
| node_relationship_config | reference | sn_grc_rel_config_node_rel_config |
| sys_id | GUID |  |
| tooltip | field_name |  |

### sn_grc_rel_config_edge_status_config -- Connector status configuration

| Field | Type | References |
| --- | --- | --- |
| color | choice |  |
| conditions | conditions |  |
| edge_config | reference | sn_grc_rel_config_edge_config |
| edge_type | choice |  |
| label | translated_text |  |
| order | integer |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |

### sn_grc_rel_config_graph_element_base -- Graph element base configuration

| Field | Type | References |
| --- | --- | --- |
| active | boolean |  |
| field_mapping | json |  |
| main_node_ui_config | reference | sn_grc_rel_config_main_node_ui_config |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |

### sn_grc_rel_config_main_node_config -- Main node configuration

| Field | Type | References |
| --- | --- | --- |
| active | boolean |  |
| conditions | conditions |  |
| max_levels | integer |  |
| max_nodes | integer |  |
| name | string |  |
| source | string |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| table | table_name |  |

### sn_grc_rel_config_main_node_ui_config -- Nexus map configuration

| Field | Type | References |
| --- | --- | --- |
| active | boolean |  |
| main_node_config | reference | sn_grc_rel_config_main_node_config |
| name | string |  |
| node_ui_type | choice |  |
| short_description | string |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| workspace_type | choice |  |

### sn_grc_rel_config_node_config -- Node configuration

| Field | Type | References |
| --- | --- | --- |
| context_record | field_name |  |
| data_nav_config | reference | sn_data_navigator_config |
| icon | reference | st_sys_design_system_icon |
| primary_label | field_name |  |
| secondary_label | field_name |  |
| set_as_main_node_ui_config | reference | sn_grc_rel_config_main_node_ui_config |
| sys_id | GUID |  |
| table | table_name |  |
| tooltip | field_name |  |

### sn_grc_rel_config_node_rel_config -- Node relationship configuration

| Field | Type | References |
| --- | --- | --- |
| active | boolean |  |
| direction | string |  |
| main_node_config | reference | sn_grc_rel_config_main_node_config |
| max_children | integer |  |
| max_levels | integer |  |
| name | string |  |
| order | string |  |
| query_category | string |  |
| rel_registry | reference | sn_data_registry_relationship |
| relationship_conditions | conditions |  |
| relationship_table | table_name |  |
| sequence | integer |  |
| sort_by | field_name |  |
| source_table | table_name |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
| target_conditions | conditions |  |
| target_ref_field | field_name |  |
| target_table | table_name |  |
| type | string |  |

### sn_grc_rel_config_node_status_config -- Node status configuration

| Field | Type | References |
| --- | --- | --- |
| color | choice |  |
| conditions | conditions |  |
| icon | reference | st_sys_design_system_icon |
| node_config | reference | sn_grc_rel_config_node_config |
| order | integer |  |
| sys_domain | domain_id |  |
| sys_domain_path | domain_path |  |
| sys_id | GUID |  |
