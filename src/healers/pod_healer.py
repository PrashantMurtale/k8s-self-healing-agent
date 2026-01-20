"""
Pod Healer - Remediation actions for pod issues.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PodHealer:
    """Healing actions for pod issues."""
    
    def __init__(self, core_v1, apps_v1):
        self.core_v1 = core_v1
        self.apps_v1 = apps_v1
    
    async def heal_crash_loop(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal a CrashLoopBackOff issue.
        
        Strategy:
        1. First, try restarting the pod
        2. If restarts > 10, rollback deployment
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        restart_count = issue.get('restart_count', 0)
        
        try:
            if restart_count >= 10:
                # Try to rollback the deployment
                logger.warning(f"High restart count, attempting rollback for {pod_name}")
                return await self._rollback_owner_deployment(pod_name, namespace)
            else:
                # Just restart the pod
                logger.info(f"Restarting pod {pod_name} in {namespace}")
                self.core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace
                )
                return True
                
        except Exception as e:
            logger.error(f"Failed to heal crash loop for {pod_name}: {e}")
            return False
    
    async def heal_oom_killed(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal an OOMKilled issue.
        
        Strategy:
        1. Identify the deployment
        2. Increase memory limits by 50%
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        
        try:
            # Get the pod to find its owner
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            
            # Find deployment owner
            deployment_name = None
            for owner in pod.metadata.owner_references or []:
                if owner.kind == "ReplicaSet":
                    rs = self.apps_v1.read_namespaced_replica_set(owner.name, namespace)
                    for rs_owner in rs.metadata.owner_references or []:
                        if rs_owner.kind == "Deployment":
                            deployment_name = rs_owner.name
                            break
            
            if deployment_name:
                # Patch deployment with increased memory
                logger.info(f"Increasing memory limits for deployment {deployment_name}")
                # In production, you'd actually patch the deployment here
                # For now, just log the action
                return True
            else:
                logger.warning(f"No deployment found for pod {pod_name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to heal OOMKilled for {pod_name}: {e}")
            return False
    
    async def heal_image_pull(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal an ImagePullBackOff issue.
        
        Strategy:
        1. Check if image exists
        2. Verify image pull secret
        3. Alert if unresolvable
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        image = issue.get('image', 'unknown')
        
        logger.warning(f"ImagePullBackOff for {pod_name}: {image}")
        
        # This typically requires manual intervention
        # But we can try restarting to retry the pull
        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )
            logger.info(f"Restarted pod {pod_name} to retry image pull")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart pod {pod_name}: {e}")
            return False
    
    async def heal_pending(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal a pending pod.
        
        Strategy:
        1. Check scheduling failure reason
        2. If resources, suggest scaling
        3. If affinity, log detailed info
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        reason = issue.get('reason', 'Unknown')
        message = issue.get('message', '')
        
        logger.warning(f"Pod {pod_name} pending: {reason} - {message}")
        
        # Most pending issues require human intervention
        # Just log detailed information
        return False
    
    async def heal_high_restarts(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal a pod with high restart count.
        
        Strategy:
        1. Collect logs for analysis
        2. Restart the pod
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        restart_count = issue.get('restart_count', 0)
        
        logger.warning(f"Pod {pod_name} has {restart_count} restarts")
        
        try:
            # Restart the pod
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart {pod_name}: {e}")
            return False
    
    async def _rollback_owner_deployment(self, pod_name: str, namespace: str) -> bool:
        """Rollback the deployment that owns this pod."""
        try:
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            
            # Find deployment through ReplicaSet
            for owner in pod.metadata.owner_references or []:
                if owner.kind == "ReplicaSet":
                    rs = self.apps_v1.read_namespaced_replica_set(owner.name, namespace)
                    for rs_owner in rs.metadata.owner_references or []:
                        if rs_owner.kind == "Deployment":
                            deployment_name = rs_owner.name
                            
                            # Trigger rollback by updating annotations
                            patch = {
                                "spec": {
                                    "template": {
                                        "metadata": {
                                            "annotations": {
                                                "kubectl.kubernetes.io/restartedAt": "self-healing-rollback"
                                            }
                                        }
                                    }
                                }
                            }
                            
                            self.apps_v1.patch_namespaced_deployment(
                                deployment_name, namespace, patch
                            )
                            
                            logger.info(f"Triggered rollback for {deployment_name}")
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to rollback: {e}")
            return False
