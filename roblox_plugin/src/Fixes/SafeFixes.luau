-- Deliberately constrained repairs for ImportValidator findings.
local SafeFixes = {}

local function rootCandidate(model: Model): BasePart?
	for _, name in { "HumanoidRootPart", "LowerTorso", "Torso", "UpperTorso" } do
		local part = model:FindFirstChild(name)
		if part and part:IsA("BasePart") then
			return part
		end
	end
	return nil
end

function SafeFixes.setPrimaryPart(model: Model): boolean
	if model.PrimaryPart then
		return false
	end
	local candidate = rootCandidate(model)
	if not candidate then
		return false
	end
	model.PrimaryPart = candidate
	return true
end

function SafeFixes.insertHumanoidRootPart(model: Model, rigType: "R6" | "R15"): BasePart?
	if model:FindFirstChild("HumanoidRootPart") then
		SafeFixes.setPrimaryPart(model)
		return nil
	end
	local _, size = model:GetBoundingBox()
	local torso = model:FindFirstChild(rigType == "R15" and "LowerTorso" or "Torso")
	if not torso or not torso:IsA("BasePart") then
		return nil
	end
	local root = Instance.new("Part")
	root.Name = "HumanoidRootPart"
	root.Size = Vector3.new(math.max(1, size.X * 0.3), math.max(1, size.Y * 0.3), math.max(1, size.Z * 0.3))
	root.CFrame = torso.CFrame
	root.CanCollide = false
	root.Transparency = 1
	root.Anchored = false
	root.Parent = model
	local motor = Instance.new("Motor6D")
	motor.Name = rigType == "R15" and "Root" or "RootJoint"
	motor.Part0 = root
	motor.Part1 = torso
	motor.Parent = root
	model.PrimaryPart = root
	return root
end

function SafeFixes.renameCaseOnlyNearMisses(model: Model, rigType: "R6" | "R15"): number
	local names = rigType == "R15"
		and { "HumanoidRootPart", "LowerTorso", "UpperTorso", "Head", "Root", "Waist", "Neck" }
		or { "HumanoidRootPart", "Torso", "Head", "RootJoint", "Neck", "Left Shoulder", "Right Shoulder", "Left Hip", "Right Hip" }
	local changed = 0
	for _, expected in names do
		for _, item in model:GetDescendants() do
			if item.Name:lower() == expected:lower() and item.Name ~= expected then
				item.Name = expected
				changed += 1
				break
			end
		end
	end
	return changed
end

function SafeFixes.apply(model: Model, rigType: "R6" | "R15", insertRoot: boolean): number
	local changes = 0
	if insertRoot and SafeFixes.insertHumanoidRootPart(model, rigType) then
		changes += 1
	end
	if SafeFixes.setPrimaryPart(model) then
		changes += 1
	end
	changes += SafeFixes.renameCaseOnlyNearMisses(model, rigType)
	return changes
end

return SafeFixes
