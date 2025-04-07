package main

import (
	"bytes"
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
)

func main() {
	if len(os.Args) < 3 {
		log.Fatalf("Usage: <image> <db_json_path>")
	}
	image := os.Args[1]
	dbJsonPath := os.Args[2]

	fmt.Printf("pgEdge Image: %s\n", image)
	fmt.Printf("DB JSON Path: %s\n", dbJsonPath)

	ctx := context.Background()

	// Create Docker client
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		log.Fatalf("Error creating Docker client: %v", err)
	}

	// Create a container with a mounted volume for db.json
	resp, err := cli.ContainerCreate(ctx, &container.Config{
		Image: image,
		Tty:   true,
	}, &container.HostConfig{
		Binds: []string{fmt.Sprintf("%s:/home/pgedge/db.json", dbJsonPath)},
	}, nil, nil, "")
	if err != nil {
		log.Fatalf("Error creating container: %v", err)
	}
	containerID := resp.ID
	fmt.Printf("Container created with ID: %s\n", containerID)

	// Start the container
	if err := cli.ContainerStart(ctx, containerID, container.StartOptions{}); err != nil {
		log.Fatalf("Error starting container: %v", err)
	}
	fmt.Println("Container started")

	time.Sleep(5 * time.Second) // Wait for a few seconds to ensure the container is ready

	// Execute commands inside the container with expected output function
	tests := []struct {
		name           string
		cmd            string
		expectedOutput func(exitCode int, output string) error
	}{
		{
			name: "pgedge can connect via PGPASS",
			cmd:  "psql -U pgedge -t -A -d defaultdb -c 'SELECT 42'",
			expectedOutput: func(exitCode int, output string) error {
				if output != "42\n" {
					return fmt.Errorf("unexpected output: %s", output)
				}
				if exitCode != 0 {
					return fmt.Errorf("unexpected exit code: %d", exitCode)
				}

				return nil
			},
		},
		// Verify spock is installed
		{
			name: "spock is installed",
			cmd:  "psql -U pgedge -t -A -d defaultdb -c \"SELECT count(*) FROM spock.subscription;\"",
			expectedOutput: func(exitCode int, output string) error {
				if output != "0\n" {
					return fmt.Errorf("unexpected output: %s", output)
				}
				if exitCode != 0 {
					return fmt.Errorf("unexpected exit code: %d", exitCode)
				}
				return nil
			},
		},
		{
			name: "LOLOR is installed",
			cmd:  "psql -U pgedge -t -A -d defaultdb -c \"SELECT lo_create (200000);;\"",
			expectedOutput: func(exitCode int, output string) error {
				if output != "200000\n" {
					return fmt.Errorf("unexpected output: %s", output)
				}
				if exitCode != 0 {
					return fmt.Errorf("unexpected exit code: %d", exitCode)
				}
				return nil
			},
		},
		{
			name: "pgvector can be installed",
			cmd:  "psql -q -U pgedge -t -A -d defaultdb -c \"CREATE EXTENSION vector; SELECT '[1, 2, 3]'::vector <-> '[4, 5, 6]'::vector;\" 2>/dev/null",
			expectedOutput: func(exitCode int, output string) error {
				if output != "5.196152422706632\n" {
					return fmt.Errorf("unexpected output: %s", output)
				}
				if exitCode != 0 {
					return fmt.Errorf("unexpected exit code: %d", exitCode)
				}
				return nil
			},
		},
		{
			name: "postgis can be installed",
			cmd:  "psql -q -U pgedge -t -A -d defaultdb -c \"CREATE EXTENSION postgis; SELECT ST_Distance(ST_Point(1, 1), ST_Point(4, 5));\" 2>/dev/null",
			expectedOutput: func(exitCode int, output string) error {
				if output != "5\n" {
					return fmt.Errorf("unexpected output: %s", output)
				}
				if exitCode != 0 {
					return fmt.Errorf("unexpected exit code: %d", exitCode)
				}
				return nil
			},
		},
	}

	// Check a set of users and make sure they can connect
	// to the database and execute a simple query
	// and check if the database is accessible
	users := []struct {
		username string
		password string
	}{
		{"admin", "uFR44yr69C4mZa72g3JQ37GX"},
		{"app", "0Osh8bqE5EokT3I3Z78MQ344"},
		{"pgedge", "z1Zsku10a91RS526jnVrLC39"},
	}

	for _, user := range users {
		name := fmt.Sprintf("%s can connect", user.username)
		cmd := fmt.Sprintf("PGPASSWORD=%s psql -U %s -t -A -d defaultdb -c 'SELECT 1'", user.password, user.username)
		tests = append(tests, struct {
			name           string
			cmd            string
			expectedOutput func(exitCode int, output string) error
		}{
			name: name,
			cmd:  cmd,
			expectedOutput: func(exitCode int, output string) error {
				if output != "1\n" {
					return fmt.Errorf("unexpected output: %s", output)
				}
				if exitCode != 0 {
					return fmt.Errorf("unexpected exit code: %d", exitCode)
				}

				return nil
			},
		})
	}

	errorCount := 0
	for _, test := range tests {
		fmt.Printf("Running test: %s", test.name)

		execID, err := cli.ContainerExecCreate(ctx, containerID, container.ExecOptions{
			Cmd:          []string{"sh", "-c", test.cmd},
			AttachStdout: true,
			AttachStderr: true,
		})
		if err != nil {
			log.Fatalf("Error creating exec: %v", err)
		}

		resp, err := cli.ContainerExecAttach(ctx, execID.ID, container.ExecAttachOptions{})
		if err != nil {
			log.Fatalf("Error attaching to exec: %v", err)
		}
		defer resp.Close()

		var outputBuf bytes.Buffer
		_, err = stdcopy.StdCopy(&outputBuf, os.Stderr, resp.Reader)
		if err != nil {
			log.Printf("Error copying output: %v", err)
		}
		output := outputBuf.String()

		// Inspect the exec to get the exit code
		inspectResp, err := cli.ContainerExecInspect(ctx, execID.ID)
		if err != nil {
			log.Fatalf("Error inspecting exec: %v", err)
		}

		// Validate the output using the expectedOutput function
		if err := test.expectedOutput(inspectResp.ExitCode, string(output)); err != nil {
			errorCount++
			fmt.Print(" ❌\n")
			log.Printf("Validation failed for command '%s': %v", test.cmd, err)
		} else {
			fmt.Print(" ✅\n")
		}
	}

	// Print a summary of the test results
	fmt.Printf("\nTest Summary:\n")
	fmt.Printf("Total Tests Executed: %d\n", len(tests))
	fmt.Printf("Total Errors: %d\n", errorCount)
	if errorCount == 0 {
		fmt.Println("✅ All tests passed successfully!")
	} else {
		fmt.Println("❌ Some tests failed. Please check the logs for details.")
		os.Exit(1)
	}
	fmt.Println("")

	// Stop and remove the container
	if err := cli.ContainerStop(ctx, containerID, container.StopOptions{}); err != nil {
		log.Printf("Error stopping container: %v", err)
	}
	fmt.Println("Container stopped")

	if err := cli.ContainerRemove(ctx, containerID, container.RemoveOptions{}); err != nil {
		log.Fatalf("Error removing container: %v", err)
	}
	fmt.Println("Container removed")

}
