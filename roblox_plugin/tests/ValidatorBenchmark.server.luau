-- Deterministic Studio benchmark. It creates 1,000 temporary R6 models,
-- validates them with real Roblox Instances, prints metrics, then destroys them.
local ServerScriptService = game:GetService("ServerScriptService")

local ImportValidator = require(ServerScriptService.ImportValidator.Checks.ImportValidator)

local CONFIG = {
	rigType = "R6",
	namingPattern = "^SM_[%w_]+$",
	minStuds = 0.1,
	maxStuds = 100,
}

local function makeR6(name: string): Model
	local model = Instance.new("Model")
	model.Name = name
	Instance.new("Humanoid").Parent = model
	for _, partName in { "HumanoidRootPart", "Torso", "Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg" } do
		local part = Instance.new("Part")
		part.Name = partName
		part.Parent = model
		if partName == "HumanoidRootPart" then
			part.CanCollide = false
			part.Transparency = 1
			model.PrimaryPart = part
		end
	end
	for jointName, parentName in {
		RootJoint = "HumanoidRootPart", Neck = "Torso", ["Left Shoulder"] = "Torso",
		["Right Shoulder"] = "Torso", ["Left Hip"] = "Torso", ["Right Hip"] = "Torso",
	} do
		local joint = Instance.new("Motor6D")
		joint.Name = jointName
		joint.Parent = model:FindFirstChild(parentName)
	end
	return model
end

local cases = {
	{ label = "clean", expected = nil, apply = function() end },
	{
		label = "case_only_name",
		expected = "naming_convention",
		apply = function(model)
			model.Name = model.Name:gsub("SM_", "sm_")
		end,
	},
	{
		label = "scale_over_by_0_01_stud",
		expected = "scale_out_of_range",
		apply = function(model)
			model.Torso.Size = Vector3.new(100.01, 2, 1)
		end,
	},
	{
		label = "root_transparency_0_99",
		expected = "rig_rootpart_properties",
		apply = function(model)
			model.HumanoidRootPart.Transparency = 0.99
		end,
	},
	{
		label = "missing_primary_part",
		expected = "missing_primary_part",
		apply = function(model)
			model.PrimaryPart = nil
		end,
	},
	{
		label = "misparented_neck_joint",
		expected = "rig_motor_structure",
		apply = function(model)
			model.Torso.Neck.Parent = model
		end,
	},
}
local total, truePositive, falsePositive, falseNegative = 0, 0, 0, 0
local elapsed = 0
local folder = Instance.new("Folder")
folder.Name = "AssetValidatorBenchmarkTemporary"
folder.Parent = workspace

for _, case in cases do
	for index = 1, 250 do
		local model = makeR6("SM_" .. case.label .. tostring(index))
		case.apply(model)
		model.Parent = folder
		local started = os.clock()
		local findings = ImportValidator.validate({ model }, CONFIG, function()
			return nil
		end)
		elapsed += os.clock() - started
		total += 1
		local found = false
		for _, finding in findings do
			if finding.issue == case.expected then
				found = true
			end
		end
		if case.expected == nil then
			if #findings > 0 then
				falsePositive += 1
			end
		elseif found then
			truePositive += 1
		else
			falseNegative += 1
		end
	end
end

folder:Destroy()
local precision = truePositive / math.max(1, truePositive + falsePositive)
local recall = truePositive / math.max(1, truePositive + falseNegative)
local f1 = 2 * precision * recall / math.max(0.000001, precision + recall)
print(string.format(
	"VALIDATOR_BENCHMARK models=%d clean=%d broken=%d boundary_cases=%d precision=%.3f recall=%.3f f1=%.3f avg_ms=%.3f total_ms=%.3f",
	total, 250, total - 250, #cases - 1, precision, recall, f1, elapsed * 1000 / total, elapsed * 1000
))
