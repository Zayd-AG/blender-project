local ImportValidator = require(script.Parent.Parent.ImportValidator.Checks.ImportValidator)

local CONFIG = { rigType = "R6", namingPattern = "^SM_[%w_]+$", minStuds = 0.1, maxStuds = 100 }
local RIG_CONFIG = { rigType = "R6", namingPattern = "^.*$", minStuds = 0.1, maxStuds = 100 }
local EMPTY_MESH = { GetVertices = function() return { 1, 2, 3 } end, GetFaces = function() return { 1 } end }

local function cleanR6()
	local model = Instance.new("Model")
	model.Name = "SM_Rig"
	Instance.new("Humanoid").Parent = model
	for _, name in { "HumanoidRootPart", "Torso", "Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg" } do
		local part = Instance.new("MeshPart")
		part.Name = name
		part.Parent = model
		if name == "HumanoidRootPart" then part.CanCollide = false; part.Transparency = 1; model.PrimaryPart = part end
	end
	for motor, parentName in { RootJoint = "HumanoidRootPart", Neck = "Torso", ["Left Shoulder"] = "Torso", ["Right Shoulder"] = "Torso", ["Left Hip"] = "Torso", ["Right Hip"] = "Torso" } do
		local joint = Instance.new("Motor6D"); joint.Name = motor; joint.Parent = model:FindFirstChild(parentName)
	end
	return model
end

return function()
	it("accepts a clean R6 fixture", function()
		local rig = cleanR6()
		expect(#ImportValidator.validate({ rig }, RIG_CONFIG, function() return EMPTY_MESH end)).to.equal(0)
		rig:Destroy()
	end)

	it("uses the selected R15 profile", function()
		local rig = Instance.new("Model"); rig.Name = "SM_R15"; Instance.new("Humanoid").Parent = rig
		local root = Instance.new("MeshPart"); root.Name = "HumanoidRootPart"; root.CanCollide = false; root.Transparency = 1; root.Parent = rig; rig.PrimaryPart = root
		for _, name in { "LowerTorso", "UpperTorso", "Head", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg", "RightFoot" } do local part = Instance.new("MeshPart"); part.Name = name; part.Parent = rig end
		for motor, parentName in { Root = "HumanoidRootPart", Waist = "LowerTorso", Neck = "UpperTorso" } do local joint = Instance.new("Motor6D"); joint.Name = motor; joint.Parent = rig:FindFirstChild(parentName) end
		local r15 = { rigType = "R15", namingPattern = "^.*$", minStuds = 0.1, maxStuds = 100 }
		expect(#ImportValidator.validate({ rig }, r15, function() return EMPTY_MESH end)).to.equal(0)
		rig:Destroy()
	end)

	it("flags only a missing HumanoidRootPart alongside an otherwise complete rig", function()
		local rig = cleanR6(); rig.HumanoidRootPart:Destroy()
		local findings = ImportValidator.validate({ rig }, RIG_CONFIG, function() return EMPTY_MESH end)
		expect(#findings > 0).to.equal(true)
		expect(findings[1].issue).to.equal("missing_primary_part")
		rig:Destroy()
	end)

	it("flags naming, scale, and missing primary part", function()
		local model = Instance.new("Model"); model.Name = "Bad Name"
		local part = Instance.new("Part"); part.Name = "Bad Part"; part.Size = Vector3.new(200, 1, 1); part.Parent = model
		local findings = ImportValidator.validate({ model }, CONFIG, function() return nil end)
		expect(#findings > 2).to.equal(true)
		model:Destroy()
	end)
end
