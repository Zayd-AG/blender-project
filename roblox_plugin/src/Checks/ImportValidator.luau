-- Pure imported-asset checks. UI and Selection access belong outside this module.

local ImportValidator = {}

export type Finding = {
	instanceName: string,
	issue: string,
	severity: "low" | "medium" | "high",
	description: string,
	autoFixable: boolean,
}

export type Config = {
	rigType: "R6" | "R15",
	namingPattern: string,
	minStuds: number,
	maxStuds: number,
}

local RIGS = {
	R6 = {
		parts = { "HumanoidRootPart", "Torso", "Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg" },
		motors = { RootJoint = "HumanoidRootPart", Neck = "Torso", ["Left Shoulder"] = "Torso", ["Right Shoulder"] = "Torso", ["Left Hip"] = "Torso", ["Right Hip"] = "Torso" },
	},
	R15 = {
		parts = { "HumanoidRootPart", "LowerTorso", "UpperTorso", "Head", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg", "RightFoot" },
		motors = { Root = "HumanoidRootPart", Waist = "LowerTorso", Neck = "UpperTorso" },
	},
}

local function add(findings: { Finding }, instance: Instance, issue: string, severity: "low" | "medium" | "high", description: string, autoFixable: boolean)
	table.insert(findings, { instanceName = instance.Name, issue = issue, severity = severity, description = description, autoFixable = autoFixable })
end

local function isStandardRigInstance(instance: Instance, rigType: "R6" | "R15"): boolean
	if instance:IsA("Humanoid") then return true end
	local profile = RIGS[rigType]
	if table.find(profile.parts, instance.Name) then return true end
	return profile.motors[instance.Name] ~= nil
end

function ImportValidator.summarizeMeshCounts(instances: { Instance }, getEditableMesh: (MeshPart) -> any?): { [string]: { vertices: number, triangles: number } }
	local totals = {}
	for _, root in instances do
		local model = root:IsA("Model") and root or root:FindFirstAncestorOfClass("Model")
		if model then
			totals[model.Name] = totals[model.Name] or { vertices = 0, triangles = 0 }
		end
		for _, descendant in { root, table.unpack(root:GetDescendants()) } do
			if descendant:IsA("MeshPart") then
				local editableMesh = getEditableMesh(descendant)
				if editableMesh and model then
					totals[model.Name].vertices += #editableMesh:GetVertices()
					totals[model.Name].triangles += #editableMesh:GetFaces()
				end
			end
		end
	end
	return totals
end

local function checkRig(model: Model, config: Config, findings: { Finding })
	if not model:FindFirstChildOfClass("Humanoid") then return end
	local profile = RIGS[config.rigType]
	for _, name in profile.parts do
		if not model:FindFirstChild(name) then
			local suggestion = nil
			for _, candidate in model:GetDescendants() do if candidate.Name:lower() == name:lower() then suggestion = candidate.Name; break end end
			local description = "Missing " .. name .. " for " .. config.rigType .. "."
			if suggestion then description ..= " Possible case-only match: " .. suggestion .. "." end
			add(findings, model, "rig_missing_part", "high", description, name == "HumanoidRootPart")
		end
	end
	local root = model:FindFirstChild("HumanoidRootPart")
	if root and root:IsA("BasePart") and (root.CanCollide or root.Transparency ~= 1) then
		add(findings, root, "rig_rootpart_properties", "medium", "HumanoidRootPart must have CanCollide false and Transparency 1.", true)
	end
	for motorName, parentName in profile.motors do
		local parent = model:FindFirstChild(parentName)
		local motor = parent and parent:FindFirstChild(motorName)
		if not motor or not motor:IsA("Motor6D") then
			add(findings, model, "rig_motor_structure", "high", "Motor6D " .. motorName .. " must be parented to " .. parentName .. ".", false)
		end
	end
end

function ImportValidator.validate(instances: { Instance }, config: Config, getEditableMesh: (MeshPart) -> any?): { Finding }
	local findings = {}
	local checkedModels = {}
	for _, root in instances do
		for _, instance in { root, table.unpack(root:GetDescendants()) } do
			local model = instance:FindFirstAncestorOfClass("Model")
			local isRigChild = model and model:FindFirstChildOfClass("Humanoid") and isStandardRigInstance(instance, config.rigType)
			if not isRigChild and instance.Name:match(config.namingPattern) == nil then
				add(findings, instance, "naming_convention", "low", "Name does not match the shared naming pattern.", false)
			end
		end
		local model = root:IsA("Model") and root or root:FindFirstAncestorOfClass("Model")
		if model and not checkedModels[model] then
			checkedModels[model] = true
			if not model.PrimaryPart then add(findings, model, "missing_primary_part", "medium", "Model has no PrimaryPart.", true) end
			local size = model:GetExtentsSize()
			if math.min(size.X, size.Y, size.Z) < config.minStuds or math.max(size.X, size.Y, size.Z) > config.maxStuds then
				add(findings, model, "scale_out_of_range", "medium", "Model dimensions are outside the configured stud range.", true)
			end
			checkRig(model, config, findings)
		end
	end
	ImportValidator.summarizeMeshCounts(instances, getEditableMesh)
	return findings
end

return ImportValidator
