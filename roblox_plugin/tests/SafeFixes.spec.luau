local SafeFixes = require(script.Parent.Parent.src.Fixes.SafeFixes)

return function()
	it("does not insert HumanoidRootPart without opt-in", function()
		local model = Instance.new("Model"); local torso = Instance.new("Part"); torso.Name = "Torso"; torso.Parent = model
		expect(SafeFixes.apply(model, "R6", false)).to.equal(1)
		expect(model:FindFirstChild("HumanoidRootPart")).to.equal(nil)
		model:Destroy()
	end)

	it("inserts a configured HumanoidRootPart only when requested", function()
		local model = Instance.new("Model"); local torso = Instance.new("Part"); torso.Name = "Torso"; torso.Parent = model
		SafeFixes.apply(model, "R6", true)
		local root = model:FindFirstChild("HumanoidRootPart")
		expect(root).never.to.equal(nil)
		expect(model.PrimaryPart).to.equal(root)
		expect(root.CanCollide).to.equal(false)
		model:Destroy()
	end)
end
