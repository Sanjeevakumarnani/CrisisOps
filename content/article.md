# CrisisOps: Giving Emergency Response Teams a Memory

In a fast-moving disaster, information changes constantly. A report that was correct an hour ago may be incomplete now. Teams need to know not only what is happening, but what has already been tried, which constraints shaped earlier decisions, and what resources are actually available.

CrisisOps is designed around that operational gap. It creates a structured common picture for locations, affected people, needs, resources, responders, transport constraints and local conditions. More importantly, it gives that picture memory.

The system stores operational events as durable memory and uses Hindsight to recall relevant history before a response plan is reviewed. The memory contains concrete facts such as attempted actions, outcomes, resource commitments and route restrictions. A plan review can therefore surface patterns that would otherwise be lost in separate reports.

The key demonstration is a before-and-after workflow. Without memory, the baseline advice is generic: verify needs, check resources, assess routes and coordinate teams. With memory, CrisisOps can surface similar situations, recurring bottlenecks, transport constraints, resource conflicts and evidence from earlier events.

The interface is deliberately designed like an operations console rather than a chatbot. The top layer shows the common operational picture: events, affected people, open needs, resource capacity, responders and blocked routes. The timeline and map-like operational views provide context, while the memory review page makes the effect of historical knowledge explicit.

CrisisOps also keeps a human in the loop. It never autonomously dispatches people or resources. It records uncertainty and provenance, and high-impact choices remain with trained responders.

The most important lesson is that memory is not useful merely because it exists. It has to be visible at the point where a decision is being considered. CrisisOps therefore puts recall and reflection directly inside the response-plan workflow.

The demo data is synthetic. A production system would need stronger source verification, access controls, resilient infrastructure, identity management, offline workflows and careful governance around sensitive humanitarian information. Those limitations are intentional: the prototype demonstrates the memory architecture and operational workflow without pretending that synthetic data is live disaster truth.
