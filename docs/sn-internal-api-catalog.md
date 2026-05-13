# ServiceNow Internal Scripted REST API Catalog

Reverse-engineered from a Zurich PDI on 2026-05-13. Discovered via `sys_ws_definition` + `sys_ws_operation` tables -- both readable with regular admin auth, no special role needed.

**Totals:** 120 services, 218 operations, 69 categories.

These endpoints are NOT documented in SN's public REST API reference. They power SN's own UI Builder apps (Application Manager, Now Assist panels, Admin Center, etc.) and side-step table-level ACLs that block direct REST table access.

Use them at your own risk -- they can change between SN releases.

## Discovery method

```bash
# 1. Find all active scripted REST API definitions
GET /api/now/table/sys_ws_definition?sysparm_query=active=true

# 2. Find all operations linked to one definition
GET /api/now/table/sys_ws_operation?sysparm_query=web_service_definition={sys_id}

# 3. The base_uri + relative_path forms the callable URL
```

## Catalog (grouped by namespace prefix)

### `global` (1 services, 1 ops)

**Inbound Event** -- `/api/global/em`
- `GET /api/global/em/inbound_event` -- Inbound Event Get

### `piwb` (1 services, 2 ops)

**PIWB API** -- `/api/piwb/piwb_api`
- `GET /api/piwb/piwb_api/get_pc_data` -- Get Precision/Coverage Values
- `POST /api/piwb/piwb_api/migration/migrate` -- Migrate Legacy PI solution to PIWB

### `sbom` (1 services, 1 ops)

**SBOM REST Api** -- `/api/sbom/core`
- `GET /api/sbom/core/upload/status` -- Upload status

### `sn_admin` (1 services, 1 ops)

**Admin Center API** -- `/api/sn_admin_center/adminx`
- `GET /api/sn_admin_center/adminx/check_updates` -- Admin Center Apps Update Available

### `sn_ads` (1 services, 2 ops)

**SNHelpSetupPlayerService** -- `/api/sn_ads_setup/play`
- `GET /api/sn_ads_setup/play/pd_lane/descriptions/{context_lane_sys_ids}` -- Get PAD Lanes Description
- `POST /api/sn_ads_setup/play/autocomplete/{sys_id}` -- Autocomplete setup

### `sn_ae` (2 services, 2 ops)

**App Generation api ** -- `/api/sn_ae_gen_ai/app_generation_api`
- `GET /api/sn_ae_gen_ai/app_generation_api/getPreviewByObjectiveId` -- Get Preview By Objective

**Skill Configurations API** -- `/api/sn_ae_recsum/skillconfigs`
- `POST /api/sn_ae_recsum/skillconfigs/util` -- util

### `sn_aemc` (4 services, 4 ops)

**AEMC Tabs API** -- `/api/sn_aemc/aemc_tabs_api`
- `GET /api/sn_aemc/aemc_tabs_api/request_tables` -- GET Request Tables

**AEMC Applications API** -- `/api/sn_aemc/applications`
- `GET /api/sn_aemc/applications/{aemc_application_sys_id}/scope` -- GET scope

**AEMC License API** -- `/api/sn_aemc/license`
- `GET /api/sn_aemc/license/` -- GET Customer License

**AEMC Scan Readiness API** -- `/api/sn_aemc/readiness`
- `POST /api/sn_aemc/readiness/app/{app_sys_id}/start` -- POST Readiness App Scan

### `sn_agent` (1 services, 5 ops)

**Agent Client Collector API** -- `/api/sn_agent/agents`
- `GET /api/sn_agent/agents/check_defs/{check_def_id}` -- getCheckDef
- `GET /api/sn_agent/agents/policy/deactivate/{policy_id}` -- deactivatePublishedPolicy
- `GET /api/sn_agent/agents/{agent_id}/restart` -- restart
- `POST /api/sn_agent/agents/check_instances/{check_instance_id}/test` -- testCheckInstance
- `POST /api/sn_agent/agents/update/check_secure_param/{param_id}` -- updateCheckSecureParam

### `sn_aia` (3 services, 3 ops)

**AI Agent A2A API ** -- `/api/sn_aia/a2a`
- `GET /api/sn_aia/a2a/v1/notification/{history_id}` -- AI Agent A2A Callback URL

**AI Agent Access Analyzer** -- `/api/sn_aia/ai_agent_access_analyzer`
- `POST /api/sn_aia/ai_agent_access_analyzer/check_acl` -- checkACL

**AI Worker API** -- `/api/sn_aia/ai_worker_api`
- `POST /api/sn_aia/ai_worker_api/feedback` -- feedback

### `sn_aiops` (1 services, 1 ops)

**AI Insights** -- `/api/sn_aiops_ai_agents/ai_insights`
- `POST /api/sn_aiops_ai_agents/ai_insights/trigger` -- trigger

### `sn_apm` (4 services, 5 ops)

**Architectural Artifact** -- `/api/sn_apm_mdtl/architectural_artifact`
- `POST /api/sn_apm_mdtl/architectural_artifact/update_access_list` -- Update Access List

**Diagram Instance** -- `/api/sn_apm_mdtl/diagram_instance`
- `GET /api/sn_apm_mdtl/diagram_instance/v1/compare_versions/{versionA}/{versionB}/{granularity}/{diagramType}` -- Compare diagram versions
- `POST /api/sn_apm_mdtl/diagram_instance/v1/set_instance_name/{instanceId}` -- Set Instance Name

**BA LifeCycle Timeline** -- `/api/sn_apm_ws/ba_lifecycle_timeline`
- `POST /api/sn_apm_ws/ba_lifecycle_timeline/v1/get_trm_hierarchy` -- getTRMHierarchy

**Business Capability Hierarchy** -- `/api/sn_apm_ws/business_capability_hierarchy`
- `POST /api/sn_apm_ws/business_capability_hierarchy/v1/update_portfolio_plan` -- updatePortfolioPlan

### `sn_app` (7 services, 20 ops)

**App Engine Studio Applications API** -- `/api/sn_app_eng_studio/applications`
- `GET /api/sn_app_eng_studio/applications/{application_sys_id}/{table_name}/files/{object_sys_ids}` -- GET Application File

**Generic API** -- `/api/sn_app_eng_studio/generic`
- `GET /api/sn_app_eng_studio/generic/commit_mode_properties` -- Get Commit Mode Properties
- `GET /api/sn_app_eng_studio/generic/license_validation_status` -- Get AES License Status

**App Engine Studio Plugin Activations** -- `/api/sn_app_eng_studio/plugin_activations`
- `GET /api/sn_app_eng_studio/plugin_activations/active_plugin_version` -- Active Plugin Version

**App Engine Studio Resources Content API** -- `/api/sn_app_eng_studio/resources_content`
- `GET /api/sn_app_eng_studio/resources_content/` -- GET Resources Content

**Secops UI Annotations ** -- `/api/sn_app_secops_ui/annotations`
- `GET /api/sn_app_secops_ui/annotations/getAnnotations/{table_name}/{toTable}/{label}/{record_id}` -- getAnnotations

**Secops UI SI Actions** -- `/api/sn_app_secops_ui/secops_ui_si_actions`
- `POST /api/sn_app_secops_ui/secops_ui_si_actions/escalate` -- Escalate
- `POST /api/sn_app_secops_ui/secops_ui_si_actions/qradar/createSIR` -- IBM QRadar Offense Ingestion Create SIR
- `POST /api/sn_app_secops_ui/secops_ui_si_actions/view_details_in_external_system` -- View Details in External System

**Security Incident Util** -- `/api/sn_app_secops_ui/secops_ui_util`
- `GET /api/sn_app_secops_ui/secops_ui_util/email_template/{table}` -- Email Template
- `GET /api/sn_app_secops_ui/secops_ui_util/get_asmt_fulfilment/{sys_id}` -- Get Assessments Fulfilment
- `GET /api/sn_app_secops_ui/secops_ui_util/is_user_admin` -- is_user_admin
- `GET /api/sn_app_secops_ui/secops_ui_util/process_definition_states` -- Process Definition States
- `GET /api/sn_app_secops_ui/secops_ui_util/related_list_definitions` -- Related List Definitions
- `GET /api/sn_app_secops_ui/secops_ui_util/sightings_for_incident/{incident_id}` -- Sightings for Incident
- `GET /api/sn_app_secops_ui/secops_ui_util/valid_states/{sys_id}` -- Valid States
- `PATCH /api/sn_app_secops_ui/secops_ui_util/response_task_state/{table_name}/{sys_id}/{state}` -- Response Task State
- `POST /api/sn_app_secops_ui/secops_ui_util/construct_si_action_modal_params` -- Construct Params for SI Action Modal
- `POST /api/sn_app_secops_ui/secops_ui_util/email_search` -- Perform Email Search
- `POST /api/sn_app_secops_ui/secops_ui_util/related_list_query_count` -- Related List Query Count

### `sn_appclient` (1 services, 4 ops)

**AppManager(Internal API)** -- `/api/sn_appclient/appmanager`
- `GET /api/sn_appclient/appmanager/app_info_from_store/{sourceAppId}/{version}` -- GetAppDetailsFromStore
- `GET /api/sn_appclient/appmanager/progress/{trackerId}` -- Execution Status
- `POST /api/sn_appclient/appmanager/apps` -- GetApps
- `POST /api/sn_appclient/appmanager/plugins` -- GetPlugins

### `sn_apw` (2 services, 2 ops)

**Enterprise Agile Planning** -- `/api/sn_apw_advanced/enterprise_agile_planning`
- `POST /api/sn_apw_advanced/enterprise_agile_planning/create_span_entry` -- Create span entry

**New Docs Component Helper** -- `/api/sn_apw_advanced/new_docs_component_helper`
- `GET /api/sn_apw_advanced/new_docs_component_helper/templatedata` -- GetTemplateData

### `sn_auto` (1 services, 1 ops)

**Automation Discovery Report API** -- `/api/sn_auto_discovery/report`
- `GET /api/sn_auto_discovery/report/topics` -- Related Topics

### `sn_awh` (1 services, 1 ops)

**AWH Configs** -- `/api/sn_awh_config/awh_configs`
- `GET /api/sn_awh_config/awh_configs/configs/{endpointPath}` -- Get Configs By Endpoint Path

### `sn_bcp` (1 services, 1 ops)

**BCM Item Picker Modal Util** -- `/api/sn_bcp/bcm_item_picker_modal_util`
- `GET /api/sn_bcp/bcm_item_picker_modal_util/getItemsToInclude` -- Get Items To Include

### `sn_build` (1 services, 4 ops)

**Build Agent API** -- `/api/sn_build_agent/build_agent_api`
> Rest API for build agent extension to interact with Instance
- `GET /api/sn_build_agent/build_agent_api/conversations/{id}/messages` -- Get Messages
- `GET /api/sn_build_agent/build_agent_api/getTableSchema/{table}` -- Get Table Schema
- `GET /api/sn_build_agent/build_agent_api/providerConfig` -- Get Provider Configuration
- `POST /api/sn_build_agent/build_agent_api/telemetry` -- Telemetry

### `sn_cd` (2 services, 2 ops)

**Audience** -- `/api/sn_cd/audience`
- `POST /api/sn_cd/audience/total_count` -- Get Audiences Count

**Ownership** -- `/api/sn_cd/ownership`
- `GET /api/sn_cd/ownership/my_audiences` -- Get Audience Ownership

### `sn_cdm` (3 services, 8 ops)

**CdmApplicationsApi** -- `/api/sn_cdm/applications`
> Allows a user to upload or export config data, manage deployables
- `GET /api/sn_cdm/applications/deployables/exports/{export_id}/status` -- Get export status
- `POST /api/sn_cdm/applications/deployables/exports` -- Export
- `POST /api/sn_cdm/applications/uploads/components/file` -- Upload to components file node
- `PUT /api/sn_cdm/applications/uploads/deployables` -- Upload to deployables - Internal

**CdmEditorApi** -- `/api/sn_cdm/editor`
> Allows a user to work with nodes
- `DELETE /api/sn_cdm/editor/nodes` -- Delete node
- `POST /api/sn_cdm/editor/includes` -- Create include
- `POST /api/sn_cdm/editor/nodes` -- Create node

**CdmSnapshotApi** -- `/api/sn_cdm/snapshots`
> Allows a user to work with a snapshot of a deployable
- `PUT /api/sn_cdm/snapshots/validate` -- Validate snapshot by name

### `sn_ce` (1 services, 1 ops)

**Comments** -- `/api/sn_ce/comments`
- `GET /api/sn_ce/comments/{commentId}/replies` -- Get replies

### `sn_change` (1 services, 2 ops)

**CAB Workbench (Internal API)** -- `/api/sn_change_cab/cab`
- `GET /api/sn_change_cab/cab/approval/{taskId}` -- Approval Info
- `POST /api/sn_change_cab/cab/agenda/item/{agendaItemId}/promote` -- UPDATE Agenda Item Promote

### `sn_chat` (1 services, 1 ops)

**Chat Core REST Service** -- `/api/sn_chat_collab/chat_core_rest_service`
- `POST /api/sn_chat_collab/chat_core_rest_service/performChatAction` -- Perform Chat Action

### `sn_chg` (2 services, 6 ops)

**Change Management** -- `/api/sn_chg_rest/change`
> Process level Change Request REST API
- `DELETE /api/sn_chg_rest/change/{sys_id}/conflict` -- Conflict - Cancel
- `GET /api/sn_chg_rest/change/emergency` -- Emergency - search
- `PATCH /api/sn_chg_rest/change/{sys_id}/approvals` -- Approvals
- `PATCH /api/sn_chg_rest/change/{sys_id}/risk` -- Risk - Calculate

**Change Schedule (Internal)** -- `/api/sn_chg_soc/soc`
- `POST /api/sn_chg_soc/soc/removePermission` -- removePermission
- `POST /api/sn_chg_soc/soc/updateSchedule` -- updateSchedule

### `sn_cld` (3 services, 5 ops)

**CCM Cumulus Intg Core** -- `/api/sn_cld_intg_core/ccm_cumulus_intg_core`
- `POST /api/sn_cld_intg_core/ccm_cumulus_intg_core/node_records` -- Insert Node Records
- `POST /api/sn_cld_intg_core/ccm_cumulus_intg_core/tag_names` -- Create Tag Names

**Cloud Integrations Core** -- `/api/sn_cld_intg_core/cloud_billing_core`
- `POST /api/sn_cld_intg_core/cloud_billing_core/get_or_create_bill_node` -- Get or Create Billing Node
- `POST /api/sn_cld_intg_core/cloud_billing_core/get_or_update_execution_status` -- Get Or Update Execution Status

**Cloud Integrations Core** -- `/api/sn_cld_intg_core/cloud_core`
- `GET /api/sn_cld_intg_core/cloud_core/providers` -- Get All Providers

### `sn_clin` (5 services, 10 ops)

**Cloud Insights AWS Rightsizing** -- `/api/sn_clin_aws/right_sizing`
- `DELETE /api/sn_clin_aws/right_sizing/custom_metric` -- Delete custom metrics

**Cloud Insights Common** -- `/api/sn_clin_core/clin_cmn`
- `GET /api/sn_clin_core/clin_cmn/all_resource_groups` -- Get all resource groups
- `GET /api/sn_clin_core/clin_cmn/linked_accounts_for_parent` -- Get linked accounts for parent account
- `GET /api/sn_clin_core/clin_cmn/overall_cfg_status` -- Get landing page info
- `GET /api/sn_clin_core/clin_cmn/refresh_budgets` -- Refresh Budgets
- `GET /api/sn_clin_core/clin_cmn/should_refresh_budget` -- Should Refresh Budget

**Cloud Insights Reserved Instance** -- `/api/sn_clin_core/ri_recommendation`
- `GET /api/sn_clin_core/ri_recommendation/terms` -- Get all Term Options
- `PUT /api/sn_clin_core/ri_recommendation/decline_recommendations` -- Decline RI Recommendations

**Cloud Insights Right Sizing** -- `/api/sn_clin_core/right_sizing`
- `GET /api/sn_clin_core/right_sizing/policy_types` -- Get all policy types

**Cloud Insights Unused Resources** -- `/api/sn_clin_core/unused_machines`
- `DELETE /api/sn_clin_core/unused_machines/exclusion` -- Exclusions

### `sn_cmdb` (2 services, 3 ops)

**AI Assets API** -- `/api/sn_cmdb_foundation/asset`
- `GET /api/sn_cmdb_foundation/asset/ai_dataset/{sys_id}` -- AI Dataset
- `GET /api/sn_cmdb_foundation/asset/ai_prompt/{sys_id}` -- AI Prompt

**CMDB Workspace API (scoped)** -- `/api/sn_cmdb_ws/cmdb_workspace_api_scoped`
> An API for the CMDB Workspace scoped app intended for all endpoints.
- `POST /api/sn_cmdb_ws/cmdb_workspace_api_scoped/nlq/suggest` -- Suggest NLQ Search

### `sn_coaching` (1 services, 1 ops)

**Coaching** -- `/api/sn_coaching/coaching`
- `POST /api/sn_coaching/coaching/update_asmt_related_items` -- update_asmt_related_items

### `sn_collab` (1 services, 1 ops)

**Collaboration Tasks API** -- `/api/sn_collab_request/collaboration_tasks_api`
- `POST /api/sn_collab_request/collaboration_tasks_api/app/{application_sys_id}` -- Invite Collaborators (v2)

### `sn_comm` (1 services, 1 ops)

**Task Communication Management** -- `/api/sn_comm_management/task_communication_management`
- `GET /api/sn_comm_management/task_communication_management/channels` -- channels

### `sn_communities` (1 services, 7 ops)

**Community** -- `/api/sn_communities/community`
- `DELETE /api/sn_communities/community/profile/actions/{action_id}` -- Actions
- `GET /api/sn_communities/community/contents/types` -- Contents
- `GET /api/sn_communities/community/contents/{contentId}` -- Contents
- `GET /api/sn_communities/community/permissions/user/{userId}/forum/{forumId}` -- Get Forum Permissions for User
- `GET /api/sn_communities/community/profiles/{profileId}` -- Profile
- `POST /api/sn_communities/community/contents/harvest/{contentId}` -- Harvest Knowledge
- `POST /api/sn_communities/community/featuredContent` -- Featured Content

### `sn_config` (1 services, 1 ops)

**Configuration Hub API** -- `/api/sn_config_hub/configuration_hub_api`
- `GET /api/sn_config_hub/configuration_hub_api/config/record_scope/{table}/{recordId}` -- Get Record Scope

### `sn_conv` (1 services, 2 ops)

**Conversational flows and actions** -- `/api/sn_conv_fa/operations`
- `GET /api/sn_conv_fa/operations/getCompatibilityStatus/{table}/{sysId}` -- getCompatibilityStatus
- `POST /api/sn_conv_fa/operations/runBulkCompatibilityCheck` -- runBulkCompatibilityCheck

### `sn_convo` (1 services, 1 ops)

**Conversational Studio** -- `/api/sn_convo_studio/conversational_studio`
- `POST /api/sn_convo_studio/conversational_studio/initiate_migration_items` -- initiateTopicMigration

### `sn_cs` (1 services, 1 ops)

**VA Designer Config** -- `/api/sn_cs_builder/va_designer_config`
- `GET /api/sn_cs_builder/va_designer_config/` -- Fetch VA Designer Config

### `sn_csm` (1 services, 1 ops)

**Engagement Center API** -- `/api/sn_csm_ec/engagement_center_api`
- `PUT /api/sn_csm_ec/engagement_center_api/modules/{module_id}` -- updateModuleConfig

### `sn_cti` (1 services, 1 ops)

**CTI API** -- `/api/sn_cti_core/cti_api`
- `POST /api/sn_cti_core/cti_api/providers/{provider}/components/{component}/versions/{version}` -- CTI Operation

### `sn_cwm` (1 services, 13 ops)

**Collaborative Work Management API** -- `/api/sn_cwm/cwm_api`
- `DELETE /api/sn_cwm/cwm_api/delete_import_config/{configId}` -- Delete Import Config
- `POST /api/sn_cwm/cwm_api/apply_template/board` -- Apply template board
- `POST /api/sn_cwm/cwm_api/create_folder` -- Create folder
- `POST /api/sn_cwm/cwm_api/create_space` -- Create space
- `POST /api/sn_cwm/cwm_api/duplicate_doc` -- Duplicate doc
- `POST /api/sn_cwm/cwm_api/get_sprint_tasks/board_id/{boardId}/sprint_id/{sprintId}` -- Get Sprint Data
- `POST /api/sn_cwm/cwm_api/handle_action` -- Handle context menu action
- `POST /api/sn_cwm/cwm_api/handle_backlog_action/board_id/{boardId}` -- Handle backlog actions
- `POST /api/sn_cwm/cwm_api/moveItem` -- MoveItem
- `POST /api/sn_cwm/cwm_api/save_template` -- Save Template
- `POST /api/sn_cwm/cwm_api/searchTasks/board_id/{boardId}` -- Search tasks in sprint planning
- `POST /api/sn_cwm/cwm_api/send_notification_custom_task` -- Send notification for custom tasks
- `POST /api/sn_cwm/cwm_api/update_space_permissions` -- Update permissions of cwm space

### `sn_data` (1 services, 1 ops)

**Data Fabric UI** -- `/api/sn_data_fabric/data_fabric_ui`
- `GET /api/sn_data_fabric/data_fabric_ui/current-application-scope` -- CurrentApplicationScope

### `sn_deploy` (1 services, 1 ops)

**Deployment Pipeline API** -- `/api/sn_deploy_pipeline/deployment_pipeline_api`
- `GET /api/sn_deploy_pipeline/deployment_pipeline_api/validate_configuration` -- Validate Configuration

### `sn_devops` (1 services, 5 ops)

**DevOps** -- `/api/sn_devops/devops`
- `GET /api/sn_devops/devops/orchestration/pipelineInfo` -- Orchestration Tool | PipelineInfo Get v2
- `POST /api/sn_devops/devops/admin` -- Admin | Post
- `POST /api/sn_devops/devops/config/updatePipeline` -- Config DataMapper | Post
- `POST /api/sn_devops/devops/orchestration/changeControl` -- Orchestration Tool | Change | Post
- `PUT /api/sn_devops/devops/change-reference` -- DevOpsChangeReference | Put

### `sn_devstudio` (2 services, 5 ops)

**System** -- `/api/sn_devstudio/system`
- `GET /api/sn_devstudio/system/files` -- List Files

**VCS** -- `/api/sn_devstudio/vcs`
- `DELETE /api/sn_devstudio/vcs/apps/{appId}/repos/{repoId}/stashes/{stashId}` -- Delete Stash
- `GET /api/sn_devstudio/vcs/apps/{appId}/changes/updateSetHistory` -- Has Completed Update Set History
- `GET /api/sn_devstudio/vcs/apps/{appId}/repos/{repoId}/branches` -- List Branches
- `GET /api/sn_devstudio/vcs/storeapps` -- Get App Customization Capable Store Apps

### `sn_doc` (1 services, 1 ops)

**Document GenAI** -- `/api/sn_doc_gen_ai/genai`
- `GET /api/sn_doc_gen_ai/genai/skill_configurations` -- Get Skill Configurations

### `sn_docs` (1 services, 5 ops)

**Doc Component API** -- `/api/sn_docs/sn_doc_component_api`
- `GET /api/sn_docs/sn_doc_component_api/getRecordField` -- Get Record Field
- `GET /api/sn_docs/sn_doc_component_api/getSysProps` -- Get System Properties
- `GET /api/sn_docs/sn_doc_component_api/verifySkillConfig` -- Verify skill config
- `POST /api/sn_docs/sn_doc_component_api/emailRequest` -- Launch Email Request
- `POST /api/sn_docs/sn_doc_component_api/exportAsPdf` -- Export as PDF

### `sn_dpr` (1 services, 3 ops)

**Digital Product Release API** -- `/api/sn_dpr/digital_product_release`
- `GET /api/sn_dpr/digital_product_release/release_target` -- Get All Release Targets
- `POST /api/sn_dpr/digital_product_release/product_enhancement` -- Create Product Enhancement
- `POST /api/sn_dpr/digital_product_release/template` -- Create Template

### `sn_dt` (1 services, 1 ops)

**Dynamic Translation (Internal API)** -- `/api/sn_dt/dynamic_translation`
- `POST /api/sn_dt/dynamic_translation/get_dynamic_translation` -- GetDynamicTranslation

### `sn_egd` (4 services, 6 ops)

**egd_Conversation** -- `/api/sn_egd_act/egd_conversation`
- `GET /api/sn_egd_act/egd_conversation/employees/{sysId}/recent_conversations` -- Recent Conversations

**Aspirations** -- `/api/sn_egd_core/aspirations`
- `DELETE /api/sn_egd_core/aspirations/{sys_id}` -- Delete aspiration
- `GET /api/sn_egd_core/aspirations/{sys_id}` -- Get aspiration

**Employee Growth Plans** -- `/api/sn_egd_core/growth_plans`
- `GET /api/sn_egd_core/growth_plans/growth_plans/{growth_plan_sys_id}/activities/{activity_sys_id}` -- Get plan activity
- `POST /api/sn_egd_core/growth_plans/growth_plan/prompt` -- Create GP from prompt

**Leader Hub** -- `/api/sn_egd_lh/leader_hub`
- `POST /api/sn_egd_lh/leader_hub/talentOrgSearch` -- Talent Org Search

### `sn_egm` (1 services, 1 ops)

**Enterprise goal framework** -- `/api/sn_egm/enterprise_goal_framework`
- `GET /api/sn_egm/enterprise_goal_framework/v1/isGFAdvancedInstalled` -- isGFAdvancedInstalled

### `sn_em` (4 services, 4 ops)

**Get Attribute Data** -- `/api/sn_em_ai/get_attribute_data`
- `POST /api/sn_em_ai/get_attribute_data/getCisFacet` -- getCisFacet

**Event Connectors** -- `/api/sn_em_connector/em`
- `POST /api/sn_em_connector/em/inbound_event` -- Inbound Event Post

**ITOM Health Gen AI** -- `/api/sn_em_gai/itom_health_gen_ai`
- `GET /api/sn_em_gai/itom_health_gen_ai/get_alert_original_description/{alert_id}` -- Get Alert Original Description

**TBACE Tags APIs** -- `/api/sn_em_tbac/tag`
- `POST /api/sn_em_tbac/tag/` -- Create new tag

### `sn_ent` (2 services, 2 ops)

**AI Assets API** -- `/api/sn_ent/asset`
- `GET /api/sn_ent/asset/ai_system/{sys_id}` -- AI System

**Verify Entitlements** -- `/api/sn_ent_verify/verifyentitlements`
- `GET /api/sn_ent_verify/verifyentitlements/` -- GetEntitlements

### `sn_erp` (3 services, 4 ops)

**Zero Copy Connector for ERP** -- `/api/sn_erp_integration/erp_canvas`
- `GET /api/sn_erp_integration/erp_canvas/system/{sysId}/can-retrieve-data` -- Can Retrive system data
- `GET /api/sn_erp_integration/erp_canvas/transaction-log/{tlogNumber}` -- Lookup transaction log number

**Zero Copy Connector for ERP Trino** -- `/api/sn_erp_integration/erp_canvas_trino`
- `GET /api/sn_erp_integration/erp_canvas_trino/getTableMetadata/{schema}/{tableName}` -- getTableMetadata

**ERP Customization Mining** -- `/api/sn_erp_mining/app`
- `GET /api/sn_erp_mining/app/credentials` -- credentials

### `sn_esg` (1 services, 1 ops)

**Webhook** -- `/api/sn_esg_urjanet/webhook`
- `POST /api/sn_esg_urjanet/webhook/{token}` -- Webhook

### `sn_ex` (1 services, 1 ops)

**Exchange Online Webhook** -- `/api/sn_ex_online_spke/exchange_online_webhook`
- `POST /api/sn_ex_online_spke/exchange_online_webhook/` -- Webhook Handler

### `sn_ext` (1 services, 2 ops)

**XCC API** -- `/api/sn_ext_conn/xcc_api`
- `POST /api/sn_ext_conn/xcc_api/crawls/{crawl_id}/principals/deletion` -- delete_unseen_principals
- `POST /api/sn_ext_conn/xcc_api/crawls/{crawl_id}/records/failure` -- mark_subtree_as_failed

### `sn_fe` (1 services, 2 ops)

**FE Core REST Services** -- `/api/sn_fe/fe_core_rest_services`
- `POST /api/sn_fe/fe_core_rest_services/fetchData` -- Get Files Data
- `POST /api/sn_fe/fe_core_rest_services/getRecentFiles` -- Get Recent Files

### `sn_fin` (1 services, 1 ops)

**Finance Common** -- `/api/sn_fin/common`
- `POST /api/sn_fin/common/ds/{scriptName}/{methodName}` -- Access Finance Common Data

### `sn_g` (1 services, 1 ops)

**Guided App Creator API** -- `/api/sn_g_app_creator/guided_app_creator_api`
- `GET /api/sn_g_app_creator/guided_app_creator_api/excel_spreadsheet_columns` -- GET Excel Spreadsheet Columns

### `sn_glider` (1 services, 2 ops)

**Sync Service** -- `/api/sn_glider/sync`
- `POST /api/sn_glider/sync/files` -- Files
- `POST /api/sn_glider/sync/state` -- State

### `sn_grc` (6 services, 9 ops)

**Compliance content** -- `/api/sn_grc_cim/content`
> Compliance API to import records in Policy and Compliance tables
- `POST /api/sn_grc_cim/content/compliance/batch/cancel` -- Cancel batch
- `POST /api/sn_grc_cim/content/compliance/insert` -- Insert policy staging records

**Risk event api** -- `/api/sn_grc_pred_intel/risk_event_api`
- `POST /api/sn_grc_pred_intel/risk_event_api/associate` -- Associate risk events

**External Taxonomy REST API Access** -- `/api/sn_grc_taxonomy/external_taxonomy`
- `GET /api/sn_grc_taxonomy/external_taxonomy/getClassMapping/{providerId}` -- Get class mapping
- `GET /api/sn_grc_taxonomy/external_taxonomy/getProviderInfo` -- Get provider info
- `GET /api/sn_grc_taxonomy/external_taxonomy/getTaxonomyClasses/{providerId}` -- Get taxonomy classes

**Internal Taxonomy REST API Access** -- `/api/sn_grc_taxonomy/internal_taxonomy`
- `GET /api/sn_grc_taxonomy/internal_taxonomy/getInternalTaxonomy/{internalTaxonomyClass}` -- Get internal taxonomy data

**baselineControlTailoring** -- `/api/sn_grc_workspace/baselinecontroltailoring`
- `GET /api/sn_grc_workspace/baselinecontroltailoring/getAvailableCommonControls` -- getAvailableCommonControls

**compositeEntityApi** -- `/api/sn_grc_workspace/compositeentityapi`
- `GET /api/sn_grc_workspace/compositeentityapi/searchContentTree` -- searchContentTree

### `sn_guest` (1 services, 1 ops)

**CSM walk-up appointment** -- `/api/sn_guest_walkup_cs/csm_walk_up_appointment`
- `POST /api/sn_guest_walkup_cs/csm_walk_up_appointment/availability` -- Availability

### `sn_hr` (4 services, 5 ops)

**HR REST API** -- `/api/sn_hr_core/hr_rest_api`
- `GET /api/sn_hr_core/hr_rest_api/get_usa_employee_profile` -- Get USA Employee Profile
- `GET /api/sn_hr_core/hr_rest_api/gethrserviceusercount` -- Get Matching HR Service User Count

**Employee Files** -- `/api/sn_hr_ef/employee_files`
- `POST /api/sn_hr_ef/employee_files/create_document_audit` -- Create document audit trail

**Builder** -- `/api/sn_hr_le/builder`
- `POST /api/sn_hr_le/builder/get_new_activity_set` -- Get New Activity Set

**HR Workspace Approvals** -- `/api/sn_hr_ws/approvals`
- `PUT /api/sn_hr_ws/approvals/approve` -- Approve

### `sn_ind` (2 services, 2 ops)

**Trouble Ticket Open API** -- `/api/sn_ind_tsm_sdwan/ticket`
- `PATCH /api/sn_ind_tsm_sdwan/ticket/troubleTicket/{id}` -- Update a ticket from payload

**Trouble Ticket Open API (Deprecated)** -- `/api/sn_ind_tsm_sdwan/troubleticket`
- `PATCH /api/sn_ind_tsm_sdwan/troubleticket/{ticketType}/{id}` -- Update ticket from payload (Deprecated)

### `sn_install` (1 services, 2 ops)

**Install Base Item** -- `/api/sn_install_base/integrations`
- `GET /api/sn_install_base/integrations/installbaseitems/{id}/soldproducts` -- soldproducts
- `GET /api/sn_install_base/integrations/installbaseitems/{id}/workorders` -- workorders

### `sn_int` (1 services, 7 ops)

**CMDB Integration Studio API** -- `/api/sn_int_studio/studio`
- `GET /api/sn_int_studio/studio/operation` -- getOperationGraph
- `GET /api/sn_int_studio/studio/operation/info` -- getOperationTypeAndParams
- `GET /api/sn_int_studio/studio/plugins` -- getPlugins
- `POST /api/sn_int_studio/studio/operation` -- saveOperation
- `POST /api/sn_int_studio/studio/toggleEntityMappings` -- toggleEntityMappings
- `PUT /api/sn_int_studio/studio/application_feed/{sys_id}` -- updateApplicationFeed
- `PUT /api/sn_int_studio/studio/template/{appFeedId}/{state}/{importSetId}/{copySourceId}/{previewSize}` -- setApplicationFeedState

### `sn_irm` (1 services, 2 ops)

**documentVersionsApi** -- `/api/sn_irm_shared_cmn/documentversionsapi`
- `GET /api/sn_irm_shared_cmn/documentversionsapi/getNumberOfAttachments/{tableName}/{recordSysId}` -- Get number of attachments
- `POST /api/sn_irm_shared_cmn/documentversionsapi/createDocument` -- Create Document

### `sn_itom` (3 services, 4 ops)

**ITOM Cloud Services API** -- `/api/sn_itom_cloud_svc/ics`
- `GET /api/sn_itom_cloud_svc/ics/instance-trl` -- Get Instance TRL

**Integration Details** -- `/api/sn_itom_ingest/integration_details`
- `GET /api/sn_itom_ingest/integration_details/{integration_id}` -- Get Integration Details

**Integration launchpad** -- `/api/sn_itom_integ_app/integration_launchpad`
- `POST /api/sn_itom_integ_app/integration_launchpad/deactivate_di` -- Deactivate DI
- `POST /api/sn_itom_integ_app/integration_launchpad/get_available_cribl_routes` -- Get Available Cribl Routes

### `sn_jny` (2 services, 5 ops)

**Journey Template Service** -- `/api/sn_jny/journey_template_service`
- `POST /api/sn_jny/journey_template_service/journey_templates/{template_id}/rescind` -- Rescind journey template approval 

**Unified Journey Service** -- `/api/sn_jny/unified_journey`
- `DELETE /api/sn_jny/unified_journey/users/{user_sys_id}/task_templates/{template_sys_id}` -- Delete Task Template
- `GET /api/sn_jny/unified_journey/journey_configs/{sys_id}` -- Get Journey Config
- `PATCH /api/sn_jny/unified_journey/journeys/{journey_id}/stages/{sys_id}` -- Update Journey Stage
- `POST /api/sn_jny/unified_journey/journeys` -- Create Journey

### `sn_km` (1 services, 1 ops)

**Knowledge Management Word Add-in** -- `/api/sn_km_word/knowledge_addin`
- `GET /api/sn_km_word/knowledge_addin/` -- Word addin

### `snc` (3 services, 3 ops)

**CrWF Demo Repo API** -- `/api/snc/crwf_demo_repo_api`
> Used for Setup App Repo Utility
- `POST /api/snc/crwf_demo_repo_api/setup_client_instance` -- Set up client instance

**Event Rules NonAdmin Access** -- `/api/snc/event_rules_nonadmin_access`
- `POST /api/snc/event_rules_nonadmin_access/deleteEventRules` -- deleteEventRules

**Notification Dashboard** -- `/api/snc/notification_dashboard`
- `GET /api/snc/notification_dashboard/checkworkerStatus` -- Check Worker Status

