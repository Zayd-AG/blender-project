local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local TestEZ = require(ReplicatedStorage.Packages.TestEZ)

local results = TestEZ.TestBootstrap:run({ ServerScriptService:WaitForChild("ImportValidatorTests") })
if results.failureCount > 0 then
	error(string.format("%d TestEZ test(s) failed", results.failureCount))
end
